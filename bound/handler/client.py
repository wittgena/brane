# bound.handler.client
## @lineage: bound.client
## @lineage: channel.bound.client
## @lineage: gate.bound.client
## @lineage: gate.bound.stream.client
import asyncio
import contextvars
import copy
import datetime
import inspect
import io
import itertools
import json
import logging
import os
import random
import re
import struct
import subprocess
import sys
import textwrap
import threading
import time
import traceback
import importlib.metadata
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Literal,
    Mapping,
    Optional,
    Tuple,
    Type,
    Union,
    cast,
    get_args,
)
from dataclasses import dataclass, field
from functools import lru_cache, wraps
from importlib import resources
from inspect import iscoroutine
from io import StringIO
from os.path import abspath, dirname, join
import httpx
import openai
import tiktoken
from httpx import Proxy
from httpx._utils import get_environment_proxies
from openai.lib import _parsing

from litellm.litellm_core_utils.logging_worker import GLOBAL_LOGGING_WORKER
import litellm
import litellm.litellm_core_utils
from litellm.main import completion_with_retries, acompletion_with_retries
from litellm.caching.caching import Cache
from litellm.caching.caching_handler import CachingHandlerResponse, LLMCachingHandler
from litellm.router_utils.get_retry_from_policy import get_num_retries_from_retry_policy, reset_retry_policy
from litellm.litellm_core_utils.cached_imports import get_coroutine_checker, get_litellm_logging_class, get_set_callbacks
from litellm.utils import _get_cached_llm_caching_handler

import bridge.litellm.json_validation_rule

from bound.handler.stream.chunk.builder import stream_chunk_builder
from bound.token.counter import get_modified_max_tokens
from arch.proto.phase.gate import uuid
from bridge.litellm.credential_accessor import CredentialAccessor
from anchor.model.types.llms.openai import (
    AllMessageValues,
    AllPromptValues,
    ChatCompletionAssistantToolCall,
    ChatCompletionNamedToolChoiceParam,
    ChatCompletionToolParam,
    ChatCompletionToolParamFunctionChunk,
    OpenAITextCompletionUserMessage,
    OpenAIWebSearchOptions,
)
from anchor.model.types.utils import FileTypes
from anchor.model.types.utils import CallTypes, Embedding, EmbeddingResponse, LlmProviders, LLMResponseTypes, ModelResponse
from anchor.base.utils import type_to_response_format_param
from anchor.model.provider.resolver import get_llm_provider
from bound.handler.response.metadata import update_response_metadata
from bridge.litellm.rules import Rules
from bridge.litellm.thread_pool_executor import executor
from anchor.base.exceptions import (
    APIConnectionError,
    APIError,
    AuthenticationError,
    BadRequestError,
    BudgetExceededError,
    ContentPolicyViolationError,
    ContextWindowExceededError,
    NotFoundError,
    OpenAIError,
    PermissionDeniedError,
    RateLimitError,
    ServiceUnavailableError,
    Timeout,
    UnprocessableEntityError,
    UnsupportedParamsError,
)

from watcher.plane.emitter import get_emitter
log = get_emitter("blm.utils")

_CALL_TYPE_ENUM_MAP: dict = {ct.value: ct for ct in CallTypes}

try:
    with (
        resources.files("litellm.litellm_core_utils.tokenizers")
        .joinpath("anthropic_tokenizer.json")
        .open("r", encoding="utf-8") as f
    ):
        json_data = json.load(f)
except (ImportError, AttributeError, TypeError):
    with resources.open_text(
        "litellm.litellm_core_utils.tokenizers", "anthropic_tokenizer.json"
    ) as f:
        json_data = json.load(f)

# Convert to str (if necessary)
claude_json_str = json.dumps(json_data)
LiteLLMLoggingObject = Any
CustomLogger = Any

sentry_sdk_instance = None
capture_exception = None
add_breadcrumb = None
posthog = None
slack_app = None
alerts_channel = None
heliconeLogger = None
athinaLogger = None
promptLayerLogger = None
langsmithLogger = None
logfireLogger = None
weightsBiasesLogger = None
customLogger = None
langFuseLogger = None
openMeterLogger = None
lagoLogger = None
dataDogLogger = None
prometheusLogger = None
dynamoLogger = None
s3Logger = None
greenscaleLogger = None
lunaryLogger = None
aispendLogger = None
supabaseClient = None
callback_list: Optional[List[str]] = []
user_logger_fn = None
additional_details: Optional[Dict[str, str]] = {}
local_cache: Optional[Dict[str, str]] = {}
last_fetched_at = None
last_fetched_at_keys = None

def custom_llm_setup():
    for custom_llm in litellm.custom_provider_map:
        if custom_llm["provider"] not in litellm.provider_list:
            litellm.provider_list.append(custom_llm["provider"])

        if custom_llm["provider"] not in litellm._custom_providers:
            litellm._custom_providers.append(custom_llm["provider"])

def load_credentials_from_list(kwargs: dict):
    credential_name = kwargs.get("litellm_credential_name")
    if credential_name and litellm.credential_list:
        credential_accessor = CredentialAccessor.get_credential_values(credential_name)
        for key, value in credential_accessor.items():
            if key not in kwargs:
                kwargs[key] = value

def function_setup(original_function: str, rules_obj, start_time, *args, **kwargs):
    try:
        get_coroutine_checker_fn = getattr(sys.modules[__name__], "get_coroutine_checker", None)
        if get_coroutine_checker_fn:
            coroutine_checker = get_coroutine_checker_fn()

        applied_guardrails = []
        function_id = kwargs.get("id", None)
        model = args[0] if len(args) > 0 else kwargs.get("model", None)
        call_type = original_function

        ## @removed: dynamic_callbacks를 병합하는 복잡한 로직 삭제 후 단순화
        dynamic_callbacks = kwargs.pop("callbacks", None)

        ## @simplify: 메시지 추출 로직 단순화 - 로깅 객체가 에러를 뱉지 않게만 하는 최소한의 메시지/프롬프트 추출
        messages = "default-message-value"
        if call_type in [CallTypes.completion.value, CallTypes.acompletion.value, CallTypes.anthropic_messages.value]:
            messages = args[1] if len(args) > 1 else kwargs.get("messages", messages)
            ## @removed:Gemini thought_signature 제거 로직 완벽 삭제 (가장 비효율적이었던 O(N) 순회 파트)
        elif call_type in [CallTypes.embedding.value, CallTypes.aembedding.value]:
            messages = args[1] if len(args) > 1 else kwargs.get("input", messages)
        elif call_type in [CallTypes.image_generation.value, CallTypes.aimage_generation.value, CallTypes.text_completion.value, CallTypes.atext_completion.value]:
            messages = args[0] if len(args) > 0 else kwargs.get("prompt", messages)

        stream = False
        if _is_streaming_request(kwargs=kwargs, call_type=call_type):
            stream = True

        ## @temp.sustain: LiteLLMLoggingObject 생성 (Router/Proxy가 의존하는 핵심 객체)
        get_litellm_logging_class_fn = getattr(sys.modules[__name__], "get_litellm_logging_class")
        logging_obj = get_litellm_logging_class_fn()(
            model=model,
            messages=messages,
            stream=stream,
            litellm_call_id=kwargs.get("litellm_call_id", str(uuid.uuid4())),
            litellm_trace_id=kwargs.get("litellm_trace_id"),
            function_id=function_id or "",
            call_type=call_type,
            start_time=start_time,
            dynamic_success_callbacks=dynamic_callbacks if isinstance(dynamic_callbacks, list) else None,
            dynamic_failure_callbacks=None,
            dynamic_async_success_callbacks=None,
            dynamic_async_failure_callbacks=None,
            kwargs=kwargs,
            applied_guardrails=applied_guardrails,
        )

        ## @temp.sustain: 환경변수 및 메타데이터 업데이트 
        litellm_params = {"api_base": ""}
        if "metadata" in kwargs:
            litellm_params["metadata"] = kwargs["metadata"]
        if "litellm_metadata" in kwargs and isinstance(kwargs["litellm_metadata"], dict):
            litellm_params["litellm_metadata"] = kwargs["litellm_metadata"].copy()
            if not litellm_params.get("metadata"):
                litellm_params["metadata"] = kwargs["litellm_metadata"].copy()

        logging_obj.update_environment_variables(
            model=model,
            user="",
            optional_params={},
            litellm_params=litellm_params,
            stream_options=kwargs.get("stream_options", None),
        )
        return logging_obj, kwargs
    except Exception as e:
        log.exception("CUSTOM function_setup() - Error in setup pipeline")
        raise e


async def _client_async_logging_helper(
    logging_obj: LiteLLMLoggingObject,
    result,
    start_time,
    end_time,
    is_completion_with_fallbacks: bool,
):
    if (is_completion_with_fallbacks is False):
        GLOBAL_LOGGING_WORKER.ensure_initialized_and_enqueue(
            async_coroutine=logging_obj.async_success_handler(
                result=result, start_time=start_time, end_time=end_time
            )
        )
        logging_obj.handle_sync_success_callbacks_for_async_calls(
            result=result,
            start_time=start_time,
            end_time=end_time,
        )

def check_coroutine(value) -> bool:
    get_coroutine_checker = getattr(sys.modules[__name__], "get_coroutine_checker")
    return get_coroutine_checker().is_async_callable(value)

async def async_pre_call_deployment_hook(kwargs: Dict[str, Any], call_type: str):
    try:
        typed_call_type = CallTypes(call_type)
    except ValueError:
        typed_call_type = None  # unknown call type

    modified_kwargs = kwargs.copy()

    CustomLogger = _get_cached_custom_logger()
    for callback in litellm.callbacks:
        if isinstance(callback, CustomLogger):
            result = await callback.async_pre_call_deployment_hook(
                modified_kwargs, typed_call_type
            )
            if result is not None:
                modified_kwargs = result

    return modified_kwargs

def _is_async_request(
    kwargs: Optional[dict],
    is_pass_through: bool = False,
) -> bool:
    if kwargs is None:
        return False
    if (
        kwargs.get("acompletion", False) is True
        or kwargs.get("aembedding", False) is True
        or kwargs.get("aimg_generation", False) is True
        or kwargs.get("amoderation", False) is True
        or kwargs.get("atext_completion", False) is True
        or kwargs.get("atranscription", False) is True
        or kwargs.get("arerank", False) is True
        or kwargs.get("_arealtime", False) is True
        or kwargs.get("acreate_batch", False) is True
        or kwargs.get("acreate_fine_tuning_job", False) is True
        or is_pass_through is True
    ):
        return True
    return False


_STREAMING_CALL_TYPES = frozenset(
    {
        CallTypes.generate_content_stream,
        CallTypes.agenerate_content_stream,
        CallTypes.generate_content_stream.value,
        CallTypes.agenerate_content_stream.value,
    }
)

def _is_streaming_request(
    kwargs: Dict[str, Any],
    call_type: Union[CallTypes, str],
) -> bool:
    if "stream" in kwargs and kwargs["stream"] is True:
        return True
    return call_type in _STREAMING_CALL_TYPES

_model_cost_lowercase_map: Optional[Dict[str, str]] = None

from typing_extensions import TypedDict

def acreate(*args, **kwargs):  ## Thin client to handle the acreate langchain call
    return litellm.acompletion(*args, **kwargs)

def print_args_passed_to_litellm(original_function, args, kwargs):
    try:
        # we've already printed this for acompletion, don't print for completion
        if (
            "acompletion" in kwargs
            and kwargs["acompletion"] is True
            and original_function.__name__ == "completion"
        ):
            return
        elif (
            "aembedding" in kwargs
            and kwargs["aembedding"] is True
            and original_function.__name__ == "embedding"
        ):
            return
        elif (
            "aimg_generation" in kwargs
            and kwargs["aimg_generation"] is True
            and original_function.__name__ == "img_generation"
        ):
            return

        args_str = ", ".join(map(repr, args))
        kwargs_str = ", ".join(f"{key}={repr(value)}" for key, value in kwargs.items())
    except Exception:
        # This should always be non blocking
        pass

@lru_cache(maxsize=1)
def _get_bundled_model_cost_map() -> Dict[str, Any]:
    try:
        model_cost_path = resources.files("litellm").joinpath(
            "model_prices_and_context_window_backup.json"
        )
        return json.loads(model_cost_path.read_text())
    except Exception:
        return {}


def _get_model_cost_entry_for_provider_config(
    model: str,
    provider: LlmProviders,
) -> Dict[str, Any]:
    candidate_keys = (model, f"{provider.value}/{model}")
    for model_key in candidate_keys:
        model_info = litellm.model_cost.get(model_key)
        if model_info is not None:
            return model_info

    bundled_model_cost = _get_bundled_model_cost_map()
    for model_key in candidate_keys:
        model_info = bundled_model_cost.get(model_key)
        if model_info is not None:
            return model_info
    return {}

def add_openai_metadata(
    metadata: Optional[Mapping[str, Any]],
) -> Optional[Dict[str, str]]:
    if metadata is None:
        return None
    # Only include non-hidden parameters
    visible_metadata: Dict[str, str] = {
        str(k): v
        for k, v in metadata.items()
        if k != "hidden_params" and isinstance(v, str)
    }

    # max 16 keys allowed by openai - trim down to 16
    if len(visible_metadata) > 16:
        filtered_metadata = {}
        idx = 0
        for k, v in visible_metadata.items():
            if idx < 16:
                filtered_metadata[k] = v
            idx += 1
        visible_metadata = filtered_metadata
    return visible_metadata.copy()

def client(original_function):
    Rules = getattr(sys.modules.get(__name__, sys.modules["__main__"]), "Rules", None)
    rules_obj = Rules() if Rules else None

    @wraps(original_function)
    def wrapper(*args, **kwargs):
        log.warning(f"🚨 [CUSTOM_WRAPPER: SYNC] 진입! 대상 함수: {original_function.__name__}")
        
        if "litellm_call_id" not in kwargs:
            kwargs["litellm_call_id"] = str(uuid.uuid4())

        start_time = datetime.datetime.now()
        logging_obj = kwargs.get("litellm_logging_obj", None)
        model = args[0] if len(args) > 0 else kwargs.get("model", None)
        call_type = original_function.__name__

        try:
            if logging_obj is None:
                logging_obj, kwargs = function_setup(call_type, rules_obj, start_time, *args, **kwargs)
            kwargs["litellm_logging_obj"] = logging_obj
            load_credentials_from_list(kwargs)

            log.info(f"🟢 [CUSTOM_WRAPPER: SYNC] API 원본 호출 시작 (Model: {model})")
            result = original_function(*args, **kwargs)
            end_time = datetime.datetime.now()
            log.info("🟢 [CUSTOM_WRAPPER: SYNC] API 원본 호출 성공 및 응답 수신!")

            if _is_streaming_request(kwargs=kwargs, call_type=call_type):
                if kwargs.get("complete_response") is True:
                    chunks = list(result)
                    return stream_chunk_builder(chunks, messages=kwargs.get("messages", None))
                return result

            if kwargs.get("acompletion") or kwargs.get("aembedding") or asyncio.iscoroutine(result):
                return result

            ctx = contextvars.copy_context()
            executor.submit(
                ctx.run,
                logging_obj.success_handler,
                result,
                start_time,
                end_time,
            )
            return result

        except Exception as e:
            log.error(f"🔴 [CUSTOM_WRAPPER: SYNC] API 호출 실패! 예외 즉시 발생 (Fail-fast): {str(e)}")
            end_time = datetime.datetime.now()
            if logging_obj:
                logging_obj.failure_handler(e, traceback.format_exc(), start_time, end_time)
            raise e

    @wraps(original_function)
    async def wrapper_async(*args, **kwargs):
        log.warning(f"🚨 [CUSTOM_WRAPPER: ASYNC] 진입! 대상 함수: {original_function.__name__}")
        
        if "litellm_call_id" not in kwargs:
            kwargs["litellm_call_id"] = str(uuid.uuid4())

        start_time = datetime.datetime.now()
        logging_obj = kwargs.get("litellm_logging_obj", None)
        model = args[0] if len(args) > 0 else kwargs.get("model", None)
        call_type = original_function.__name__

        kwargs.pop("_is_litellm_internal_call", None)

        try:
            if logging_obj is None:
                logging_obj, kwargs = function_setup(
                    call_type, rules_obj, start_time, *args, **kwargs
                )
            
            modified_kwargs = await async_pre_call_deployment_hook(kwargs, call_type)
            if modified_kwargs is not None:
                kwargs = modified_kwargs

            kwargs["litellm_logging_obj"] = logging_obj
            load_credentials_from_list(kwargs)

            log.info(f"🟢 [CUSTOM_WRAPPER: ASYNC] API 원본 호출 시작 (Model: {model})")
            result = await original_function(*args, **kwargs)
            end_time = datetime.datetime.now()
            log.info("🟢 [CUSTOM_WRAPPER: ASYNC] API 원본 호출 성공 및 응답 수신!")

            if _is_streaming_request(kwargs=kwargs, call_type=call_type):
                if kwargs.get("complete_response") is True:
                    chunks = [chunk async for chunk in result] if hasattr(result, '__aiter__') else list(result)
                    return stream_chunk_builder(chunks, messages=kwargs.get("messages", None))
                return result

            if call_type == CallTypes.arealtime.value:
                return result

            asyncio.create_task(
                _client_async_logging_helper(
                    logging_obj=logging_obj,
                    result=result,
                    start_time=start_time,
                    end_time=end_time,
                    is_completion_with_fallbacks=False,
                )
            )
            return result
        except Exception as e:
            log.error(f"🔴 [CUSTOM_WRAPPER: ASYNC] API 호출 실패! 예외 즉시 발생 (Fail-fast): {str(e)}")
            end_time = datetime.datetime.now()
            if logging_obj:
                try:
                    logging_obj.failure_handler(e, traceback.format_exc(), start_time, end_time)
                except Exception:
                    pass
                try:
                    await logging_obj.async_failure_handler(e, traceback.format_exc(), start_time, end_time)
                except Exception:
                    pass
            raise e

    get_coro_checker = getattr(sys.modules.get(__name__), "get_coroutine_checker", None)
    is_coroutine = get_coro_checker().is_async_callable(original_function) if get_coro_checker else asyncio.iscoroutinefunction(original_function)

    return wrapper_async if is_coroutine else wrapper