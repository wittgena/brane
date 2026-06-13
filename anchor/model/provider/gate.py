# anchor.model.provider.gate
## @lineage: channel.bound.gate
## @lineage: channel.gate
## @lineage: gate.utils
## @lineage: blm.utils
from __future__ import annotations
import ast
import asyncio
import base64
import binascii
import contextvars
import copy
import datetime
import hashlib
import inspect
import io
import itertools
import json
import logging
import os
import random  # type: ignore
import re
import struct
import subprocess
import sys
import textwrap
import threading
import time
import traceback
from dataclasses import dataclass, field
from functools import lru_cache, wraps
from importlib import resources
from inspect import iscoroutine
from io import StringIO
from os.path import abspath, dirname, join
import dotenv
import httpx
import openai
import tiktoken
from httpx import Proxy
from httpx._utils import get_environment_proxies
from openai.lib import _parsing, _pydantic
from openai.types.chat.completion_create_params import ResponseFormat
from pydantic import BaseModel
from tiktoken import Encoding
from tokenizers import Tokenizer
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

import litellm.litellm_core_utils
from litellm.caching.in_memory_cache import InMemoryCache
from litellm.llms.base_llm.base_utils import BaseLLMModelInfo, type_to_response_format_param
from bound.config.resolver import config
from bound.token.counter import get_modified_max_tokens
from bound.handler.retry import completion_with_retries, acompletion_with_retries
from bound.config.constants import (
    DEFAULT_CHAT_COMPLETION_PARAM_VALUES,
    DEFAULT_EMBEDDING_PARAM_VALUES,
    DEFAULT_MAX_LRU_CACHE_SIZE,
    MAX_TOKEN_TRIMMING_ATTEMPTS,
    MINIMUM_PROMPT_CACHE_TOKEN_COUNT,
    OPENAI_EMBEDDING_PARAMS,
)
from anchor.base.exceptions import ContextWindowExceededError
from anchor.model.types.llms.openai import AllMessageValues, ChatCompletionToolParam, ChatCompletionToolParamFunctionChunk, OpenAIWebSearchOptions
from anchor.model.types.utils import (
    CallTypes,
    # Choices,
    # Delta,
    Embedding,
    Function,
    LlmProviders,
    LlmProvidersSet,
    # Message,
    ModelInfo,
    ModelInfoBase,
    ModelResponse,
    ModelResponseStream,
    ProviderSpecificModelInfo,
    RawRequestTypedDict,
    StreamingChoices,
    TextChoices,
    TextCompletionResponse,
    # Usage,
    all_litellm_params,
)
from anchor.model.provider.manager import ProviderConfigManager, get_provider_info
from anchor.switch.params import Choices, Delta, Message, ModelResponse, ModelResponseStream, Usage

if TYPE_CHECKING:
    from litellm.caching.caching_handler import CachingHandlerResponse, LLMCachingHandler
    from litellm.llms.base_llm.files.transformation import BaseFilesConfig
    from litellm.llms.base_llm.realtime.http_transformation import BaseRealtimeHTTPConfig
    from litellm.proxy._types import AllowedModelRegion
    from litellm.litellm_core_utils.exception_mapping_utils import exception_type
    from litellm.litellm_core_utils.get_supported_openai_params import get_supported_openai_params
    from litellm.litellm_core_utils.llm_response_utils.convert_dict_to_response import (
        _handle_invalid_parallel_tool_calls,
        convert_to_model_response_object,
        convert_to_streaming_response,
        convert_to_streaming_response_async,
    )
    from litellm.litellm_core_utils.llm_response_utils.get_api_base import get_api_base
    from litellm.litellm_core_utils.llm_response_utils.response_metadata import (
        ResponseMetadata,
    )

    from anchor.model.provider.logic import get_llm_provider
    from anchor.template.common import _parse_content_for_reasoning
    from bound.handler.stream.wrapper import CustomStreamWrapper

    from litellm.litellm_core_utils.redact_messages import (
        LiteLLMLoggingObject,
        redact_message_input_output_from_logging,
    )
    from litellm.llms.base_llm.text_to_speech.transformation import BaseTextToSpeechConfig
    from litellm.llms.bedrock.common_utils import BedrockModelInfo
    from litellm.llms.cohere.common_utils import CohereModelInfo
    from litellm.llms.mistral.ocr.transformation import MistralOCRConfig

    # Type stubs for lazy-loaded functions and classes
    from litellm.litellm_core_utils.cached_imports import (
        get_coroutine_checker,
        get_litellm_logging_class,
        get_set_callbacks,
    )
    from bridge.litellm.core_helpers import (
        get_litellm_metadata_from_kwargs,
        map_finish_reason,
        process_response_headers,
    )
    from litellm.litellm_core_utils.dot_notation_indexing import (
        delete_nested_value,
        is_nested_path,
    )
    from litellm.litellm_core_utils.get_litellm_params import (
        _get_base_model_from_litellm_call_metadata,
        get_litellm_params,
    )
    from litellm.litellm_core_utils.llm_request_utils import _ensure_extra_body_is_safe
    from litellm.litellm_core_utils.llm_response_utils.get_formatted_prompt import (
        get_formatted_prompt,
    )
    from litellm.litellm_core_utils.llm_response_utils.get_headers import (
        get_response_headers,
    )
    from litellm.litellm_core_utils.llm_response_utils.response_metadata import (
        update_response_metadata,
    )
    from litellm.litellm_core_utils.rules import Rules
    from litellm.litellm_core_utils.thread_pool_executor import executor
    from litellm.llms.base_llm.anthropic_messages.transformation import (
        BaseAnthropicMessagesConfig,
    )
    from litellm.llms.base_llm.audio_transcription.transformation import (
        BaseAudioTranscriptionConfig,
    )
    from litellm.llms.custom_httpx.http_handler import AsyncHTTPHandler, HTTPHandler
    from litellm.router_utils.get_retry_from_policy import (
        get_num_retries_from_retry_policy,
        reset_retry_policy,
    )

    # Type stubs for lazy-loaded config classes and types
    from litellm.llms.base_llm.batches.transformation import BaseBatchesConfig
    from litellm.llms.base_llm.containers.transformation import BaseContainerConfig
    from litellm.llms.base_llm.embedding.transformation import BaseEmbeddingConfig
    from litellm.llms.base_llm.image_edit.transformation import BaseImageEditConfig
    from litellm.llms.base_llm.image_generation.transformation import (
        BaseImageGenerationConfig,
    )
    from litellm.llms.base_llm.image_variations.transformation import (
        BaseImageVariationConfig,
    )
    from litellm.llms.base_llm.passthrough.transformation import BasePassthroughConfig
    from litellm.llms.base_llm.realtime.transformation import BaseRealtimeConfig
    from litellm.llms.base_llm.rerank.transformation import BaseRerankConfig
    from litellm.llms.base_llm.vector_store.transformation import BaseVectorStoreConfig
    from litellm.llms.base_llm.vector_store_files.transformation import (
        BaseVectorStoreFilesConfig,
    )
    from litellm.llms.base_llm.videos.transformation import BaseVideoConfig
    from litellm.types.llms.anthropic import (
        ANTHROPIC_API_ONLY_HEADERS,
        AnthropicThinkingParam,
    )
    from litellm.types.rerank import RerankResponse
    from anchor.model.types.llms.openai import (
        ChatCompletionDeltaToolCallChunk,
        ChatCompletionToolCallChunk,
        ChatCompletionToolCallFunctionChunk,
    )
    from litellm.types.router import LiteLLM_Params

from litellm.llms.base_llm.chat.transformation import BaseConfig
from litellm.llms.base_llm.completion.transformation import BaseTextCompletionConfig
from litellm.llms.base_llm.evals.transformation import BaseEvalsAPIConfig
from anchor.base.responses.transformation import BaseResponsesAPIConfig
from litellm.llms.base_llm.skills.transformation import BaseSkillsAPIConfig
from litellm.caching.caching import (
    AzureBlobCache,
    Cache,
    QdrantSemanticCache,
    RedisCache,
    RedisSemanticCache,
    S3Cache,
)
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
    MockException
)
from channel.secret.manager import get_secret
from watcher.plane.emitter import get_emitter

CustomLogger = Any
log = get_emitter("blm.utils")
_CALL_TYPE_ENUM_MAP: dict = {ct.value: ct for ct in CallTypes}

def _get_cached_custom_logger():
    return None

try:
    # Python 3.9+
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

claude_json_str = json.dumps(json_data)

# Adjust to your specific application needs / system capabilities.
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

def _update_dictionary(existing_dict: Dict, new_dict: dict) -> dict:
    for k, v in new_dict.items():
        if v is not None:
            # Convert stringified numbers to appropriate numeric types
            if isinstance(v, str):
                existing_dict[k] = _convert_stringified_numbers(v)
            elif isinstance(v, dict):
                existing_nested_dict = existing_dict.get(k)
                if isinstance(existing_nested_dict, dict):
                    existing_nested_dict.update(v)
                    existing_dict[k] = existing_nested_dict
                else:
                    existing_dict[k] = v
            else:
                existing_dict[k] = v

    return existing_dict


def _convert_stringified_numbers(value):
    """Convert stringified numbers (including scientific notation) to appropriate numeric types."""
    if isinstance(value, str):
        try:
            # Try to convert to float first to handle scientific notation like "3e-07"
            if "e" in value.lower() or "." in value:
                return float(value)
            # Try to convert to int for whole numbers like "8192"
            else:
                return int(value)
        except (ValueError, TypeError):
            # If conversion fails, return the original string
            return value
    return value

def _should_drop_param(k, additional_drop_params) -> bool:
    if (
        additional_drop_params is not None
        and isinstance(additional_drop_params, list)
        and k in additional_drop_params
    ):
        return True  # allow user to drop specific params for a model - e.g. vllm - logit bias

    return False

def _get_non_default_params(
    passed_params: dict, default_params: dict, additional_drop_params: Optional[list]
) -> dict:
    non_default_params = {}
    for k, v in passed_params.items():
        if (
            k in default_params
            and v != default_params[k]
            and _should_drop_param(k=k, additional_drop_params=additional_drop_params)
            is False
        ):
            non_default_params[k] = v

    return non_default_params


def get_optional_params_transcription(
    model: str,
    custom_llm_provider: str,
    language: Optional[str] = None,
    prompt: Optional[str] = None,
    response_format: Optional[str] = None,
    temperature: Optional[int] = None,
    timestamp_granularities: Optional[List[Literal["word", "segment"]]] = None,
    drop_params: Optional[bool] = None,
    **kwargs,
):
    from bound.config.constants import OPENAI_TRANSCRIPTION_PARAMS

    # retrieve all parameters passed to the function
    passed_params = locals()

    passed_params.pop("OPENAI_TRANSCRIPTION_PARAMS")
    custom_llm_provider = passed_params.pop("custom_llm_provider")
    drop_params = passed_params.pop("drop_params")
    special_params = passed_params.pop("kwargs")
    for k, v in special_params.items():
        passed_params[k] = v

    default_params = {
        "language": None,
        "prompt": None,
        "response_format": None,
        "temperature": None,  # openai defaults this to 0
        "timestamp_granularities": None,
    }

    non_default_params = {
        k: v
        for k, v in passed_params.items()
        if (k in default_params and v != default_params[k])
    }
    optional_params = {}

    ## raise exception if non-default value passed for non-openai/azure embedding calls
    def _check_valid_arg(supported_params):
        if len(non_default_params.keys()) > 0:
            keys = list(non_default_params.keys())
            for k in keys:
                if (
                    drop_params is True or config.drop_params is True
                ) and k not in supported_params:  # drop the unsupported non-default values
                    non_default_params.pop(k, None)
                elif k not in supported_params:
                    raise UnsupportedParamsError(
                        status_code=500,
                        message=f"Setting user/encoding format is not supported by {custom_llm_provider}. To drop it from the call, set `litellm.drop_params = True`.",
                    )
            return non_default_params

    provider_config: Optional[BaseAudioTranscriptionConfig] = None
    if custom_llm_provider is not None:
        provider_config = ProviderConfigManager.get_provider_audio_transcription_config(
            model=model,
            provider=LlmProviders(custom_llm_provider),
        )

    if custom_llm_provider == "openai" or custom_llm_provider == "azure":
        optional_params = non_default_params
    elif custom_llm_provider == "groq":
        supported_params = config.GroqSTTConfig().get_supported_openai_params_stt()
        _check_valid_arg(supported_params=supported_params)
        optional_params = config.GroqSTTConfig().map_openai_params_stt(
            non_default_params=non_default_params,
            optional_params=optional_params,
            model=model,
            drop_params=drop_params if drop_params is not None else False,
        )
    elif provider_config is not None:  # handles fireworks ai, and any future providers
        supported_params = provider_config.get_supported_openai_params(model=model)
        _check_valid_arg(supported_params=supported_params)
        optional_params = provider_config.map_openai_params(
            non_default_params=non_default_params,
            optional_params=optional_params,
            model=model,
            drop_params=drop_params if drop_params is not None else False,
        )

    optional_params = add_provider_specific_params_to_optional_params(
        optional_params=optional_params,
        passed_params=passed_params,
        custom_llm_provider=custom_llm_provider,
        openai_params=OPENAI_TRANSCRIPTION_PARAMS,
        additional_drop_params=kwargs.get("additional_drop_params", None),
    )

    return optional_params


def _map_openai_size_to_vertex_ai_aspect_ratio(size: Optional[str]) -> str:
    """Map OpenAI size parameter to Vertex AI aspectRatio."""
    if size is None:
        return "1:1"

    # Map OpenAI size strings to Vertex AI aspect ratio strings
    # Vertex AI accepts: "1:1", "9:16", "16:9", "4:3", "3:4"
    size_to_aspect_ratio = {
        "256x256": "1:1",  # Square
        "512x512": "1:1",  # Square
        "1024x1024": "1:1",  # Square (default)
        "1792x1024": "16:9",  # Landscape
        "1024x1792": "9:16",  # Portrait
    }
    return size_to_aspect_ratio.get(
        size, "1:1"
    )  # Default to square if size not recognized


def get_optional_params_image_gen(
    model: Optional[str] = None,
    n: Optional[int] = None,
    quality: Optional[str] = None,
    response_format: Optional[str] = None,
    size: Optional[str] = None,
    style: Optional[str] = None,
    user: Optional[str] = None,
    imageConfig: Optional[dict] = None,
    custom_llm_provider: Optional[str] = None,
    additional_drop_params: Optional[list] = None,
    provider_config: Optional[BaseImageGenerationConfig] = None,
    drop_params: Optional[bool] = None,
    **kwargs,
):
    # retrieve all parameters passed to the function
    passed_params = locals()
    model = passed_params.pop("model", None)
    custom_llm_provider = passed_params.pop("custom_llm_provider")
    provider_config = passed_params.pop("provider_config", None)
    drop_params = passed_params.pop("drop_params", None)
    additional_drop_params = passed_params.pop("additional_drop_params", None)
    special_params = passed_params.pop("kwargs")
    for k, v in special_params.items():
        if k.startswith("aws_") and (
            custom_llm_provider != "bedrock" and custom_llm_provider != "sagemaker"
        ):  # allow dynamically setting boto3 init logic
            continue
        elif k == "hf_model_name" and custom_llm_provider != "sagemaker":
            continue
        elif (
            k.startswith("vertex_")
            and custom_llm_provider != "vertex_ai"
            and custom_llm_provider != "vertex_ai_beta"
        ):  # allow dynamically setting vertex ai init logic
            continue
        passed_params[k] = v

    default_params = {
        "n": None,
        "quality": None,
        "response_format": None,
        "size": None,
        "style": None,
        "user": None,
        "imageConfig": None,
    }

    non_default_params = _get_non_default_params(
        passed_params=passed_params,
        default_params=default_params,
        additional_drop_params=additional_drop_params,
    )
    optional_params: Dict[str, Any] = {}

    ## raise exception if non-default value passed for non-openai/azure embedding calls
    def _check_valid_arg(supported_params):
        if len(non_default_params.keys()) > 0:
            keys = list(non_default_params.keys())
            for k in keys:
                if (
                    config.drop_params is True or drop_params is True
                ) and k not in supported_params:  # drop the unsupported non-default values
                    non_default_params.pop(k, None)
                    passed_params.pop(k, None)
                elif k not in supported_params:
                    raise UnsupportedParamsError(
                        status_code=500,
                        message=f"Setting `{k}` is not supported by {custom_llm_provider}, {model}. To drop it from the call, set `litellm.drop_params = True`.",
                    )
            return non_default_params

    if provider_config is not None:
        supported_params = provider_config.get_supported_openai_params(
            model=model or ""
        )
        _check_valid_arg(supported_params=supported_params)
        optional_params = provider_config.map_openai_params(
            non_default_params=non_default_params,
            optional_params=optional_params,
            model=model or "",
            drop_params=drop_params if drop_params is not None else False,
        )
    elif (
        custom_llm_provider == "openai"
        or custom_llm_provider == "azure"
        or custom_llm_provider in config.openai_compatible_providers
    ):
        optional_params = non_default_params
    elif custom_llm_provider == "bedrock":
        config_class = config.BedrockImageGeneration.get_config_class(model=model)
        supported_params = config_class.get_supported_openai_params(model=model)
        _check_valid_arg(supported_params=supported_params)
        optional_params = config_class.map_openai_params(
            non_default_params=non_default_params, optional_params={}
        )
    elif custom_llm_provider == "vertex_ai":
        supported_params = ["n", "size"]
        """
        All params here: https://console.cloud.google.com/vertex-ai/publishers/google/model-garden/imagegeneration?project=adroit-crow-413218
        """
        _check_valid_arg(supported_params=supported_params)
        if n is not None:
            optional_params["sampleCount"] = int(n)

        # Map OpenAI size parameter to Vertex AI aspectRatio
        if size is not None:
            optional_params["aspectRatio"] = _map_openai_size_to_vertex_ai_aspect_ratio(
                size
            )

    openai_params: list[str] = list(default_params.keys())
    if provider_config is not None:
        supported_params = provider_config.get_supported_openai_params(
            model=model or ""
        )
        openai_params = list(supported_params)

    optional_params = add_provider_specific_params_to_optional_params(
        optional_params=optional_params,
        passed_params=passed_params,
        custom_llm_provider=custom_llm_provider or "",
        openai_params=openai_params,
        additional_drop_params=additional_drop_params,
    )
    # remove keys with None or empty dict/list values to avoid sending empty payloads
    optional_params = {
        k: v
        for k, v in optional_params.items()
        if v is not None and (not isinstance(v, (dict, list)) or len(v) > 0)
    }
    return optional_params


def get_optional_params_embeddings(  # noqa: PLR0915
    # 2 optional params
    model: str,
    user: Optional[str] = None,
    encoding_format: Optional[str] = None,
    dimensions: Optional[int] = None,
    custom_llm_provider="",
    drop_params: Optional[bool] = None,
    additional_drop_params: Optional[List[str]] = None,
    allowed_openai_params: Optional[List[str]] = None,
    **kwargs,
):
    # Lazy load get_supported_openai_params
    get_supported_openai_params = getattr(
        sys.modules[__name__], "get_supported_openai_params"
    )

    # retrieve all parameters passed to the function
    passed_params = locals()
    custom_llm_provider = passed_params.pop("custom_llm_provider", None)
    special_params = passed_params.pop("kwargs")

    drop_params = passed_params.pop("drop_params", None)
    additional_drop_params = passed_params.pop("additional_drop_params", None)
    allowed_openai_params = passed_params.pop("allowed_openai_params", None) or []
    # Remove function objects from passed_params to avoid JSON serialization errors
    passed_params.pop("get_supported_openai_params", None)

    def _check_valid_arg(supported_params: Optional[list]):
        if supported_params is None:
            return
        unsupported_params = {}
        for k in non_default_params.keys():
            if k not in supported_params:
                unsupported_params[k] = non_default_params[k]
        if unsupported_params:
            if config.drop_params is True or (
                drop_params is not None and drop_params is True
            ):
                pass
            else:
                raise UnsupportedParamsError(
                    status_code=500,
                    message=f"{custom_llm_provider} does not support parameters: {unsupported_params}, for model={model}. To drop these, set `litellm.drop_params=True` or for proxy:\n\n`litellm_settings:\n drop_params: true`\n",
                )

    non_default_params = (
        PreProcessNonDefaultParams.embedding_pre_process_non_default_params(
            passed_params=passed_params,
            special_params=special_params,
            custom_llm_provider=custom_llm_provider,
            additional_drop_params=additional_drop_params,
            model=model,
        )
    )

    provider_config: Optional[BaseEmbeddingConfig] = None

    optional_params = {}
    if provider_config is not None:
        supported_params: Optional[list] = provider_config.get_supported_openai_params(
            model=model
        )
        _check_valid_arg(supported_params=supported_params)
        optional_params = provider_config.map_openai_params(
            non_default_params=non_default_params,
            optional_params={},
            model=model,
            drop_params=drop_params if drop_params is not None else False,
        )
        # Provider-only params (e.g. Cohere input_type) are not in
        # OPENAI_EMBEDDING_PARAMS, so embedding_pre_process drops them from
        # non_default_params before map_openai_params. Restore only those extras
        # from passed_params — skip OPENAI_EMBEDDING_PARAMS to avoid duplicating
        # values already mapped (e.g. dimensions -> output_dimension).
        if supported_params:
            for param in supported_params:
                if param in OPENAI_EMBEDDING_PARAMS:
                    continue
                if (
                    param in passed_params
                    and passed_params[param] is not None
                    and param not in optional_params
                ):
                    optional_params[param] = passed_params[param]
    ## raise exception if non-default value passed for non-openai/azure embedding calls
    elif custom_llm_provider == "openai":
        # 'dimensions` is only supported in `text-embedding-3` and later models
        if (
            model is not None
            and "text-embedding-3" not in model
            and "dimensions" in non_default_params.keys()
            and "dimensions" not in (allowed_openai_params or [])
        ):
            # Honor drop_params (per-call) and litellm.drop_params (global) the same
            # way `_check_valid_arg` does above. The raised error message itself
            # tells users to set `drop_params=True`, so respect it here.
            if config.drop_params is True or drop_params is True:
                non_default_params.pop("dimensions", None)
            else:
                raise UnsupportedParamsError(
                    status_code=500,
                    message="Setting dimensions is not supported for OpenAI `text-embedding-3` and later models. To drop it from the call, set `litellm.drop_params = True`.",
                )
        optional_params = non_default_params
    elif custom_llm_provider == "vertex_ai" or custom_llm_provider == "gemini":
        supported_params = get_supported_openai_params(
            model=model,
            custom_llm_provider="vertex_ai",
            request_type="embeddings",
        )
        _check_valid_arg(supported_params=supported_params)
        (
            optional_params,
            kwargs,
        ) = config.VertexAITextEmbeddingConfig().map_openai_params(
            non_default_params=non_default_params, optional_params={}, kwargs=kwargs
        )
    elif custom_llm_provider == "ollama":
        if "dimensions" in non_default_params:
            optional_params["dimensions"] = non_default_params.pop("dimensions")
        if len(non_default_params.keys()) > 0:
            if (config.drop_params is True or drop_params is True):
                keys = list(non_default_params.keys())
                for k in keys:
                    non_default_params.pop(k, None)
            else:
                raise UnsupportedParamsError(
                    status_code=500,
                    message=f"Setting {non_default_params} is not supported by {custom_llm_provider}. To drop it from the call, set `litellm.drop_params = True`.",
                )
    elif (
        custom_llm_provider != "openai"
        and custom_llm_provider != "azure"
        and custom_llm_provider not in config.openai_compatible_providers
    ):
        if len(non_default_params.keys()) > 0:
            if (
                config.drop_params is True or drop_params is True
            ):  # drop the unsupported non-default values
                keys = list(non_default_params.keys())
                for k in keys:
                    non_default_params.pop(k, None)
            else:
                raise UnsupportedParamsError(
                    status_code=500,
                    message=f"Setting {non_default_params} is not supported by {custom_llm_provider}. To drop it from the call, set `litellm.drop_params = True`.",
                )
        else:
            optional_params = non_default_params
    else:
        optional_params = non_default_params

    final_params = add_provider_specific_params_to_optional_params(
        optional_params=optional_params,
        passed_params=passed_params,
        custom_llm_provider=custom_llm_provider,
        openai_params=list(DEFAULT_EMBEDDING_PARAM_VALUES.keys()),
        additional_drop_params=kwargs.get("additional_drop_params", None),
    )

    if "extra_body" in final_params and len(final_params["extra_body"]) == 0:
        final_params.pop("extra_body", None)

    return final_params


def _remove_additional_properties(schema):
    """
    clean out 'additionalProperties = False'. Causes vertexai/gemini OpenAI API Schema errors - https://github.com/langchain-ai/langchainjs/issues/5240

    Relevant Issues: https://github.com/BerriAI/litellm/issues/6136, https://github.com/BerriAI/litellm/issues/6088
    """
    if isinstance(schema, dict):
        # Remove the 'additionalProperties' key if it exists and is set to False
        if "additionalProperties" in schema and schema["additionalProperties"] is False:
            del schema["additionalProperties"]

        # Recursively process all dictionary values
        for key, value in schema.items():
            _remove_additional_properties(value)

    elif isinstance(schema, list):
        # Recursively process all items in the list
        for item in schema:
            _remove_additional_properties(item)

    return schema


def _remove_strict_from_schema(schema):
    """
    Relevant Issues: https://github.com/BerriAI/litellm/issues/6136, https://github.com/BerriAI/litellm/issues/6088
    """
    if isinstance(schema, dict):
        # Remove the 'additionalProperties' key if it exists and is set to False
        if "strict" in schema:
            del schema["strict"]

        # Recursively process all dictionary values
        for key, value in schema.items():
            _remove_strict_from_schema(value)

    elif isinstance(schema, list):
        # Recursively process all items in the list
        for item in schema:
            _remove_strict_from_schema(item)

    return schema


def _remove_json_schema_refs(schema, max_depth=10):
    """
    Remove JSON schema reference fields like '$id' and '$schema' that can cause issues with some providers.

    These fields are used for schema validation but can cause problems when the schema references
    are not accessible to the provider's validation system.

    Args:
        schema: The schema object to clean (dict, list, or other)
        max_depth: Maximum recursion depth to prevent infinite loops (default: 10)

    Relevant Issues: Mistral API grammar validation fails when schema contains $id and $schema references
    """
    if max_depth <= 0:
        return schema

    if isinstance(schema, dict):
        # Remove JSON schema reference fields
        schema.pop("$id", None)
        schema.pop("$schema", None)

        # Recursively process all dictionary values
        for key, value in schema.items():
            _remove_json_schema_refs(value, max_depth - 1)

    elif isinstance(schema, list):
        # Recursively process all items in the list
        for item in schema:
            _remove_json_schema_refs(item, max_depth - 1)

    return schema


def _remove_unsupported_params(
    non_default_params: dict, supported_openai_params: Optional[List[str]]
) -> dict:
    """
    Remove unsupported params from non_default_params
    """
    remove_keys = []
    if supported_openai_params is None:
        return {}  # no supported params, so no optional openai params to send
    for param in non_default_params.keys():
        if param not in supported_openai_params:
            remove_keys.append(param)
    for key in remove_keys:
        non_default_params.pop(key, None)
    return non_default_params


def filter_out_litellm_params(kwargs: dict) -> dict:
    """
    Filter out LiteLLM internal parameters from kwargs dict.

    Returns a new dict containing only non-LiteLLM parameters that should be
    passed to external provider APIs.

    Args:
        kwargs: Dictionary that may contain LiteLLM internal parameters

    Returns:
        Dictionary with LiteLLM internal parameters filtered out

    Example:
        >>> kwargs = {"query": "test", "shared_session": session_obj, "metadata": {}}
        >>> filtered = filter_out_litellm_params(kwargs)
        >>> # filtered = {"query": "test"}
    """

    return {
        key: value for key, value in kwargs.items() if key not in all_litellm_params
    }


class PreProcessNonDefaultParams:
    @staticmethod
    def base_pre_process_non_default_params(
        passed_params: dict,
        special_params: dict,
        custom_llm_provider: str,
        additional_drop_params: Optional[List[str]],
        default_param_values: dict,
        additional_endpoint_specific_params: List[str],
    ) -> dict:
        for k, v in special_params.items():
            if k.startswith("aws_") and (
                custom_llm_provider != "bedrock"
                and not custom_llm_provider.startswith("sagemaker")
            ):  # allow dynamically setting boto3 init logic
                continue
            elif k == "hf_model_name" and custom_llm_provider != "sagemaker":
                continue
            elif (
                k.startswith("vertex_")
                and custom_llm_provider != "vertex_ai"
                and custom_llm_provider != "vertex_ai_beta"
            ):  # allow dynamically setting vertex ai init logic
                continue
            passed_params[k] = v

        # filter out those parameters that were passed with non-default values
        non_default_params = {
            k: v
            for k, v in passed_params.items()
            if (
                k != "model"
                and k != "custom_llm_provider"
                and k != "api_version"
                and k != "drop_params"
                and k != "allowed_openai_params"
                and k != "additional_drop_params"
                and k not in additional_endpoint_specific_params
                and k in default_param_values
                and v != default_param_values[k]
                and _should_drop_param(
                    k=k, additional_drop_params=additional_drop_params
                )
                is False
            )
        }

        return non_default_params

    @staticmethod
    def embedding_pre_process_non_default_params(
        passed_params: dict,
        special_params: dict,
        custom_llm_provider: str,
        additional_drop_params: Optional[List[str]],
        model: str,
        remove_sensitive_keys: bool = False,
        add_provider_specific_params: bool = False,
    ) -> dict:
        non_default_params = (
            PreProcessNonDefaultParams.base_pre_process_non_default_params(
                passed_params=passed_params,
                special_params=special_params,
                custom_llm_provider=custom_llm_provider,
                additional_drop_params=additional_drop_params,
                default_param_values={k: None for k in OPENAI_EMBEDDING_PARAMS},
                additional_endpoint_specific_params=["input"],
            )
        )

        return non_default_params


def pre_process_non_default_params(
    passed_params: dict,
    special_params: dict,
    custom_llm_provider: str,
    additional_drop_params: Optional[List[str]],
    model: str,
    remove_sensitive_keys: bool = False,
    add_provider_specific_params: bool = False,
    provider_config: Optional[BaseConfig] = None,
) -> dict:
    """
    Pre-process non-default params to a standardized format
    """
    # retrieve all parameters passed to the function

    non_default_params = PreProcessNonDefaultParams.base_pre_process_non_default_params(
        passed_params=passed_params,
        special_params=special_params,
        custom_llm_provider=custom_llm_provider,
        additional_drop_params=additional_drop_params,
        default_param_values=DEFAULT_CHAT_COMPLETION_PARAM_VALUES,
        additional_endpoint_specific_params=["messages"],
    )

    if "response_format" in non_default_params:
        if provider_config is not None:
            non_default_params["response_format"] = (
                provider_config.get_json_schema_from_pydantic_object(
                    response_format=non_default_params["response_format"]
                )
            )
        else:
            non_default_params["response_format"] = type_to_response_format_param(
                response_format=non_default_params["response_format"]
            )

    if "tools" in non_default_params and isinstance(
        non_default_params, list
    ):  # fixes https://github.com/BerriAI/litellm/issues/4933
        tools = non_default_params["tools"]
        for (
            tool
        ) in (
            tools
        ):  # clean out 'additionalProperties = False'. Causes vertexai/gemini OpenAI API Schema errors - https://github.com/langchain-ai/langchainjs/issues/5240
            tool_function = tool.get("function", {})
            parameters = tool_function.get("parameters", None)
            if parameters is not None:
                new_parameters = copy.deepcopy(parameters)
                if (
                    "additionalProperties" in new_parameters
                    and new_parameters["additionalProperties"] is False
                ):
                    new_parameters.pop("additionalProperties", None)
                tool_function["parameters"] = new_parameters

    if add_provider_specific_params:
        non_default_params = add_provider_specific_params_to_optional_params(
            optional_params=non_default_params,
            passed_params=passed_params,
            custom_llm_provider=custom_llm_provider,
            openai_params=list(DEFAULT_CHAT_COMPLETION_PARAM_VALUES.keys()),
            additional_drop_params=additional_drop_params,
        )

    if remove_sensitive_keys:
        non_default_params = remove_sensitive_keys_from_dict(non_default_params)
    return non_default_params


def remove_sensitive_keys_from_dict(d: dict) -> dict:
    """
    Remove sensitive keys from a dictionary
    """
    sensitive_key_phrases = ["key", "secret", "access", "credential"]
    remove_keys = []
    for key in d.keys():
        if any(phrase in key.lower() for phrase in sensitive_key_phrases):
            remove_keys.append(key)
    for key in remove_keys:
        d.pop(key)
    return d


def pre_process_optional_params(
    passed_params: dict, non_default_params: dict, custom_llm_provider: str
) -> dict:
    """For .completion(), preprocess optional params"""
    optional_params: Dict = {}

    common_auth_dict = config.common_cloud_provider_auth_params
    if custom_llm_provider in common_auth_dict["providers"]:
        """
        Check if params = ["project", "region_name", "token"]
        and correctly translate for = ["azure", "vertex_ai", "watsonx", "aws"]
        """
        if custom_llm_provider == "azure":
            optional_params = config.AzureOpenAIConfig().map_special_auth_params(
                non_default_params=passed_params, optional_params=optional_params
            )
        elif custom_llm_provider == "bedrock":
            optional_params = (
                config.AmazonBedrockGlobalConfig().map_special_auth_params(
                    non_default_params=passed_params, optional_params=optional_params
                )
            )
        elif (
            custom_llm_provider == "vertex_ai"
            or custom_llm_provider == "vertex_ai_beta"
        ):
            optional_params = config.VertexAIConfig().map_special_auth_params(
                non_default_params=passed_params, optional_params=optional_params
            )
        elif custom_llm_provider == "watsonx":
            optional_params = config.IBMWatsonXAIConfig().map_special_auth_params(
                non_default_params=passed_params, optional_params=optional_params
            )

    ## raise exception if function calling passed in for a provider that doesn't support it
    if (
        "functions" in non_default_params
        or "function_call" in non_default_params
        or "tools" in non_default_params
    ):
        if (
            custom_llm_provider == "ollama"
            and custom_llm_provider != "text-completion-openai"
            and custom_llm_provider != "azure"
            and custom_llm_provider != "vertex_ai"
            and custom_llm_provider != "anyscale"
            and custom_llm_provider != "together_ai"
            and custom_llm_provider != "groq"
            and custom_llm_provider != "nvidia_nim"
            and custom_llm_provider != "cerebras"
            and custom_llm_provider != "xai"
            and custom_llm_provider != "ai21_chat"
            and custom_llm_provider != "volcengine"
            and custom_llm_provider != "deepseek"
            and custom_llm_provider != "codestral"
            and custom_llm_provider != "mistral"
            and custom_llm_provider != "anthropic"
            and custom_llm_provider != "cohere_chat"
            and custom_llm_provider != "cohere"
            and custom_llm_provider != "bedrock"
            and custom_llm_provider != "ollama_chat"
            and custom_llm_provider != "openrouter"
            and custom_llm_provider != "vercel_ai_gateway"
            and custom_llm_provider != "nebius"
            and custom_llm_provider != "wandb"
            and custom_llm_provider not in config.openai_compatible_providers
        ):
            if custom_llm_provider == "ollama":
                # ollama actually supports json output
                optional_params["format"] = "json"
                litellm.add_function_to_prompt = (
                    True  # so that main.py adds the function call to the prompt
                )
                if "tools" in non_default_params:
                    optional_params["functions_unsupported_model"] = (
                        non_default_params.pop("tools")
                    )
                    non_default_params.pop(
                        "tool_choice", None
                    )  # causes ollama requests to hang
                elif "functions" in non_default_params:
                    optional_params["functions_unsupported_model"] = (
                        non_default_params.pop("functions")
                    )
            elif (
                config.add_function_to_prompt
            ):  # if user opts to add it to prompt instead
                optional_params["functions_unsupported_model"] = non_default_params.pop(
                    "tools", non_default_params.pop("functions", None)
                )
            else:
                raise UnsupportedParamsError(
                    status_code=500,
                    message=f"Function calling is not supported by {custom_llm_provider}.",
                )

    return optional_params


def get_optional_params(  # noqa: PLR0915
    # use the openai defaults
    # https://platform.openai.com/docs/api-reference/chat/create
    model: str,
    functions=None,
    function_call=None,
    temperature=None,
    top_p=None,
    n=None,
    stream=False,
    stream_options=None,
    stop=None,
    max_tokens=None,
    max_completion_tokens=None,
    modalities=None,
    prediction=None,
    audio=None,
    presence_penalty=None,
    frequency_penalty=None,
    logit_bias=None,
    user=None,
    custom_llm_provider="",
    response_format=None,
    seed=None,
    tools=None,
    tool_choice=None,
    max_retries=None,
    logprobs=None,
    top_logprobs=None,
    extra_headers=None,
    api_version=None,
    parallel_tool_calls=None,
    drop_params=None,
    allowed_openai_params: Optional[List[str]] = None,
    reasoning_effort=None,
    verbosity=None,
    additional_drop_params=None,
    messages: Optional[List[AllMessageValues]] = None,
    thinking: Optional[AnthropicThinkingParam] = None,
    web_search_options: Optional[OpenAIWebSearchOptions] = None,
    safety_identifier: Optional[str] = None,
    base_model: Optional[str] = None,
    **kwargs,
):
    passed_params = locals().copy()
    special_params = passed_params.pop("kwargs")
    # Remove base_model from passed_params so it doesn't interfere with
    # non_default_params / _check_valid_arg — it's a routing hint, not an
    # OpenAI param.
    passed_params.pop("base_model", None)
    provider_config: Optional[BaseConfig] = None
    if custom_llm_provider is not None and custom_llm_provider in [
        provider.value for provider in LlmProviders
    ]:
        provider_config = ProviderConfigManager.get_provider_chat_config(
            model=model,
            provider=LlmProviders(custom_llm_provider),
            base_model=base_model,
        )
    non_default_params = pre_process_non_default_params(
        passed_params=passed_params,
        special_params=special_params,
        custom_llm_provider=custom_llm_provider,
        additional_drop_params=additional_drop_params,
        model=model,
        provider_config=provider_config,
    )
    optional_params = pre_process_optional_params(
        passed_params=passed_params,
        non_default_params=non_default_params,
        custom_llm_provider=custom_llm_provider,
    )

    def _check_valid_arg(supported_params: List[str]):
        """
        Check if the params passed to completion() are supported by the provider

        Args:
            supported_params: List[str] - supported params from the litellm config
        """
        log.info(
            f"\nLiteLLM completion() model= {model}; provider = {custom_llm_provider}"
        )
        log.debug(
            f"\nLiteLLM: Params passed to completion() {passed_params}"
        )
        log.debug(
            f"\nLiteLLM: Non-Default params passed to completion() {non_default_params}"
        )
        unsupported_params = {}
        for k in non_default_params.keys():
            if k not in supported_params:
                if k == "user" or k == "stream_options" or k == "stream":
                    continue
                if k == "n" and n == 1:  # langchain sends n=1 as a default value
                    continue  # skip this param
                if (
                    k == "max_retries"
                ):  # TODO: This is a patch. We support max retries for OpenAI, Azure. For non OpenAI LLMs we need to add support for max retries
                    continue  # skip this param
                # Always keeps this in elif code blocks
                else:
                    unsupported_params[k] = non_default_params[k]

        if unsupported_params:
            if config.drop_params is True or (
                drop_params is not None and drop_params is True
            ):
                for k in unsupported_params.keys():
                    non_default_params.pop(k, None)
            else:
                raise UnsupportedParamsError(
                    status_code=500,
                    message=f"{custom_llm_provider} does not support parameters: {list(unsupported_params.keys())}, for model={model}. To drop these, set `litellm.drop_params=True` or for proxy:\n\n`litellm_settings:\n drop_params: true`\n. \n If you want to use these params dynamically send allowed_openai_params={list(unsupported_params.keys())} in your request.",
                )

    get_supported_openai_params = getattr(
        sys.modules[__name__], "get_supported_openai_params"
    )
    supported_params = get_supported_openai_params(
        model=model, custom_llm_provider=custom_llm_provider, base_model=base_model
    )
    if supported_params is None:
        supported_params = get_supported_openai_params(
            model=model, custom_llm_provider="openai"
        )

    supported_params = supported_params or []
    allowed_openai_params = allowed_openai_params or []
    supported_params.extend(allowed_openai_params)

    _check_valid_arg(
        supported_params=supported_params or [],
    )

    ## raise exception if provider doesn't support passed in param
    if custom_llm_provider == "anthropic":
        ## check if unsupported param passed in
        optional_params = config.AnthropicConfig().map_openai_params(
            model=model,
            non_default_params=non_default_params,
            optional_params=optional_params,
            drop_params=(
                drop_params
                if drop_params is not None and isinstance(drop_params, bool)
                else False
            ),
        )
    elif custom_llm_provider == "huggingface":
        optional_params = config.HuggingFaceChatConfig().map_openai_params(
            non_default_params=non_default_params,
            optional_params=optional_params,
            model=model,
            drop_params=(
                drop_params
                if drop_params is not None and isinstance(drop_params, bool)
                else False
            ),
        )
    elif custom_llm_provider == "gemini":
        optional_params = config.GoogleAIStudioGeminiConfig().map_openai_params(
            non_default_params=non_default_params,
            optional_params=optional_params,
            model=model,
            drop_params=(
                drop_params
                if drop_params is not None and isinstance(drop_params, bool)
                else False
            ),
        )
    elif custom_llm_provider == "ollama":
        optional_params = config.OllamaConfig().map_openai_params(
            non_default_params=non_default_params,
            optional_params=optional_params,
            model=model,
            drop_params=(
                drop_params
                if drop_params is not None and isinstance(drop_params, bool)
                else False
            ),
        )
    elif custom_llm_provider == "openai":
        optional_params = config.OpenAIConfig().map_openai_params(
            non_default_params=non_default_params,
            optional_params=optional_params,
            model=model,
            drop_params=(
                drop_params
                if drop_params is not None and isinstance(drop_params, bool)
                else False
            ),
        )
    elif provider_config is not None:
        optional_params = provider_config.map_openai_params(
            non_default_params=non_default_params,
            optional_params=optional_params,
            model=model,
            drop_params=(
                drop_params
                if drop_params is not None and isinstance(drop_params, bool)
                else False
            ),
        )
    else:  # assume passing in params for openai-like api
        optional_params = config.OpenAILikeChatConfig().map_openai_params(
            non_default_params=non_default_params,
            optional_params=optional_params,
            model=model,
            drop_params=(
                drop_params
                if drop_params is not None and isinstance(drop_params, bool)
                else False
            ),
        )
    # if user passed in non-default kwargs for specific providers/models, pass them along
    optional_params = add_provider_specific_params_to_optional_params(
        optional_params=optional_params,
        passed_params=passed_params,
        custom_llm_provider=custom_llm_provider,
        openai_params=list(DEFAULT_CHAT_COMPLETION_PARAM_VALUES.keys()),
        additional_drop_params=additional_drop_params,
    )
    optional_params = _apply_openai_param_overrides(
        optional_params=optional_params,
        non_default_params=non_default_params,
        allowed_openai_params=allowed_openai_params,
    )

    # Apply nested drops from additional_drop_params
    if additional_drop_params:
        is_nested_path = getattr(sys.modules[__name__], "is_nested_path")
        delete_nested_value = getattr(sys.modules[__name__], "delete_nested_value")
        nested_paths = [p for p in additional_drop_params if is_nested_path(p)]
        for path in nested_paths:
            optional_params = delete_nested_value(optional_params, path)

    return optional_params


def add_provider_specific_params_to_optional_params(
    optional_params: dict,
    passed_params: dict,
    custom_llm_provider: str,
    openai_params: List[str],
    additional_drop_params: Optional[list] = None,
) -> dict:
    if (
        custom_llm_provider
        in ["openai", "azure", "text-completion-openai"]
        + config.openai_compatible_providers
    ):
        # for openai, azure we should pass the extra/passed params within `extra_body` https://github.com/openai/openai-python/blob/ac33853ba10d13ac149b1fa3ca6dba7d613065c9/src/openai/resources/models.py#L46
        if (
            _should_drop_param(
                k="extra_body", additional_drop_params=additional_drop_params
            )
            is False
        ):
            extra_body = dict(passed_params.pop("extra_body", None) or {})
            for k in passed_params.keys():
                if k not in openai_params and passed_params[k] is not None:
                    extra_body[k] = passed_params[k]
            if not isinstance(optional_params.get("extra_body"), dict):
                optional_params["extra_body"] = {}
            initial_extra_body = {
                **optional_params["extra_body"],
                **extra_body,
            }

            if additional_drop_params is not None:
                processed_extra_body = {
                    k: v
                    for k, v in initial_extra_body.items()
                    if k not in additional_drop_params
                }
            else:
                processed_extra_body = initial_extra_body

            _ensure_extra_body_is_safe = getattr(
                sys.modules[__name__], "_ensure_extra_body_is_safe"
            )
            optional_params["extra_body"] = _ensure_extra_body_is_safe(
                extra_body=processed_extra_body
            )
    else:
        for k in passed_params.keys():
            if k not in openai_params and passed_params[k] is not None:
                if _should_drop_param(
                    k=k, additional_drop_params=additional_drop_params
                ):
                    continue
                optional_params[k] = passed_params[k]
    return optional_params

def _apply_openai_param_overrides(optional_params: dict, non_default_params: dict, allowed_openai_params: list):
    if allowed_openai_params:
        for param in allowed_openai_params:
            if param in optional_params:
                continue
            if param not in non_default_params:
                continue
            optional_params[param] = non_default_params.pop(param)
    return optional_params

def calculate_max_parallel_requests(
    max_parallel_requests: Optional[int],
    rpm: Optional[int],
    tpm: Optional[int],
    default_max_parallel_requests: Optional[int],
) -> Optional[int]:
    if max_parallel_requests is not None:
        return max_parallel_requests
    elif rpm is not None:
        return rpm
    elif tpm is not None:
        calculated_rpm = int(tpm / 1000 * 6)
        if calculated_rpm == 0:
            calculated_rpm = 1
        return calculated_rpm
    elif default_max_parallel_requests is not None:
        return default_max_parallel_requests
    return None


def _get_deployment_order(deployment: Union[Dict, Any]) -> Optional[int]:
    """
    Returns the routing order for a deployment.

    Checks litellm_params first (static config), then model_info (dynamic/team
    models added via API where order lives in model_info, not litellm_params).
    """
    order = deployment.get("litellm_params", {}).get("order")
    if order is None:
        order = deployment.get("model_info", {}).get("order")
    return order


def _get_order_filtered_deployments(
    healthy_deployments: List[Dict], target_order: Optional[int] = None
) -> List:
    if target_order is not None:
        filtered = [
            d for d in healthy_deployments if _get_deployment_order(d) == target_order
        ]
        if filtered:
            return filtered
        # target_order doesn't match any deployment (e.g., external fallback model) — return all
        return healthy_deployments

    # Default: pick min order group
    _valid_orders: List[int] = [
        o
        for deployment in healthy_deployments
        for o in [_get_deployment_order(deployment)]
        if o is not None
    ]
    min_order: Optional[int] = min(_valid_orders) if _valid_orders else None

    if min_order is not None:
        filtered_deployments = [
            deployment
            for deployment in healthy_deployments
            if _get_deployment_order(deployment) == min_order
        ]

        return filtered_deployments
    return healthy_deployments


def _get_excluded_filtered_deployments(
    healthy_deployments: List[Dict],
    excluded_deployment_ids: Optional[Iterable[str]] = None,
) -> List:
    if not excluded_deployment_ids:
        return healthy_deployments

    excluded_set = set(excluded_deployment_ids)
    return [
        d
        for d in healthy_deployments
        if (d.get("model_info") or {}).get("id") not in excluded_set
    ]

def _get_model_region(custom_llm_provider: str, litellm_params: LiteLLM_Params) -> Optional[str]:
    return litellm_params.region_name

def _infer_model_region(litellm_params: LiteLLM_Params) -> Optional[AllowedModelRegion]:
    model, custom_llm_provider, _, _ = config.get_llm_provider(
        model=litellm_params.model, litellm_params=litellm_params
    )

    model_region = _get_model_region(
        custom_llm_provider=custom_llm_provider, litellm_params=litellm_params
    )

    if model_region is None:
        log.debug(
            "Cannot infer model region for model: {}".format(litellm_params.model)
        )
        return None

    eu_regions = []
    us_regions = []
    for region in eu_regions:
        if region in model_region.lower():
            return "eu"
    for region in us_regions:
        if region in model_region.lower():
            return "us"
    return None


def _is_region_eu(litellm_params: LiteLLM_Params) -> bool:
    """
    Return true/false if a deployment is in the EU
    """
    if litellm_params.region_name == "eu":
        return True

    ## Else - try and infer from model region
    model_region = _infer_model_region(litellm_params=litellm_params)
    if model_region is not None and model_region == "eu":
        return True
    return False


def _is_region_us(litellm_params: LiteLLM_Params) -> bool:
    """
    Return true/false if a deployment is in the US
    """
    if litellm_params.region_name == "us":
        return True

    ## Else - try and infer from model region
    model_region = _infer_model_region(litellm_params=litellm_params)
    if model_region is not None and model_region == "us":
        return True
    return False


def is_region_allowed(
    litellm_params: LiteLLM_Params, allowed_model_region: str
) -> bool:
    """
    Return true/false if a deployment is in the EU
    """
    if litellm_params.region_name == allowed_model_region:
        return True
    return False


def get_model_region(
    litellm_params: LiteLLM_Params, mode: Optional[str]
) -> Optional[str]:
    """
    Pass the litellm params for an azure model, and get back the region
    """
    if (
        "azure" in litellm_params.model
        and isinstance(litellm_params.api_key, str)
        and isinstance(litellm_params.api_base, str)
    ):
        _model = litellm_params.model.replace("azure/", "")
        response: dict = config.AzureChatCompletion().get_headers(
            model=_model,
            api_key=litellm_params.api_key,
            api_base=litellm_params.api_base,
            api_version=litellm_params.api_version or config.AZURE_DEFAULT_API_VERSION,
            timeout=10,
            mode=mode or "chat",
        )

        region: Optional[str] = response.get("x-ms-region", None)
        return region
    return None


def get_first_chars_messages(kwargs: dict) -> str:
    try:
        _messages = kwargs.get("messages")
        _messages = str(_messages)[:100]
        return _messages
    except Exception:
        return ""


def _count_characters(text: str) -> int:
    # Remove white spaces and count characters
    filtered_text = "".join(char for char in text if not char.isspace())
    return len(filtered_text)


def get_response_string(response_obj: Union[ModelResponse, ModelResponseStream]) -> str:
    # Handle Responses API streaming events
    if hasattr(response_obj, "type") and hasattr(response_obj, "response"):
        # This is a Responses API streaming event (e.g., ResponseCreatedEvent, ResponseCompletedEvent)
        # Extract text from the response object's output if available
        responses_api_response = getattr(response_obj, "response", None)
        if responses_api_response and hasattr(responses_api_response, "output"):
            output_list = responses_api_response.output
            # Use list accumulation to avoid O(n^2) string concatenation:
            # repeatedly doing `response_str += part` copies the full string each time
            # because Python strings are immutable, so total work grows with n^2.
            response_output_parts: List[str] = []
            for output_item in output_list:
                # Handle output items with content array
                if hasattr(output_item, "content"):
                    for content_part in output_item.content:
                        if hasattr(content_part, "text"):
                            response_output_parts.append(content_part.text)
                # Handle output items with direct text field
                elif hasattr(output_item, "text"):
                    response_output_parts.append(output_item.text)
            return "".join(response_output_parts)

    # Handle Responses API text delta events
    if hasattr(response_obj, "type") and hasattr(response_obj, "delta"):
        event_type = getattr(response_obj, "type", "")
        if "text.delta" in event_type or "output_text.delta" in event_type:
            delta = getattr(response_obj, "delta", "")
            return delta if isinstance(delta, str) else ""

    # Handle standard ModelResponse and ModelResponseStream
    _choices: Union[List[Choices], List[StreamingChoices]] = response_obj.choices

    # Use list accumulation to avoid O(n^2) string concatenation across choices
    response_parts: List[str] = []
    for choice in _choices:
        if isinstance(choice, Choices):
            if choice.message.content is not None:
                response_parts.append(str(choice.message.content))
        elif isinstance(choice, StreamingChoices):
            if choice.delta.content is not None:
                response_parts.append(str(choice.delta.content))

    return "".join(response_parts)


def get_api_key(llm_provider: str, dynamic_api_key: Optional[str]):
    api_key = dynamic_api_key or config.api_key
    if llm_provider == "openai" or llm_provider == "text-completion-openai":
        api_key = api_key or config.openai_key or get_secret("OPENAI_API_KEY")
    elif llm_provider == "anthropic" or llm_provider == "anthropic_text":
        api_key = api_key or config.anthropic_key or get_secret("ANTHROPIC_API_KEY")
    elif llm_provider == "huggingface":
        api_key = (
            api_key or config.huggingface_key or get_secret("HUGGINGFACE_API_KEY")
        )
    return api_key


def get_utc_datetime():
    import datetime as dt
    from datetime import datetime

    if hasattr(dt, "UTC"):
        return datetime.now(dt.UTC)  # type: ignore
    else:
        return datetime.utcnow()  # type: ignore


def get_max_tokens(model: str) -> Optional[int]:
    def _get_max_position_embeddings(model_name):
        # Construct the URL for the config.json file
        config_url = f"https://huggingface.co/{model_name}/raw/main/config.json"
        try:
            # Make the HTTP request to get the raw JSON file
            response = config.module_level_client.get(config_url)
            response.raise_for_status()  # Raise an exception for bad responses (4xx or 5xx)

            # Parse the JSON response
            config_json = response.json()
            # Extract and return the max_position_embeddings
            max_position_embeddings = config_json.get("max_position_embeddings")
            if max_position_embeddings is not None:
                return max_position_embeddings
            else:
                return None
        except Exception:
            return None

    try:
        if model in config.model_cost:
            if "max_output_tokens" in config.model_cost[model]:
                return config.model_cost[model]["max_output_tokens"]
            elif "max_tokens" in config.model_cost[model]:
                return config.model_cost[model]["max_tokens"]
        model, custom_llm_provider, _, _ = get_llm_provider(model=model)
        if custom_llm_provider == "huggingface":
            max_tokens = _get_max_position_embeddings(model_name=model)
            return max_tokens
        if model in config.model_cost:  # check if extracted model is in model_list
            if "max_output_tokens" in config.model_cost[model]:
                return config.model_cost[model]["max_output_tokens"]
            elif "max_tokens" in config.model_cost[model]:
                return config.model_cost[model]["max_tokens"]
        else:
            raise Exception()
        return None
    except Exception:
        raise Exception(
            f"Model {model} isn't mapped yet. Add it here - https://github.com/BerriAI/litellm/blob/main/model_prices_and_context_window.json"
        )


def _strip_stable_vertex_version(model_name) -> str:
    return re.sub(r"-\d+$", "", model_name)


def _get_base_bedrock_model(model_name) -> str:
    """
    Get the base model from the given model name.

    Handle model names like - "us.meta.llama3-2-11b-instruct-v1:0" -> "meta.llama3-2-11b-instruct-v1"
    AND "meta.llama3-2-11b-instruct-v1:0" -> "meta.llama3-2-11b-instruct-v1"
    """
    from litellm.llms.bedrock.common_utils import BedrockModelInfo

    return BedrockModelInfo.get_base_model(model_name)


def _strip_openai_finetune_model_name(model_name: str) -> str:
    """
    Strips the organization, custom suffix, and ID from an OpenAI fine-tuned model name.

    input: ft:gpt-3.5-turbo:my-org:custom_suffix:id
    output: ft:gpt-3.5-turbo

    Args:
    model_name (str): The full model name

    Returns:
    str: The stripped model name
    """
    return re.sub(r"(:[^:]+){3}$", "", model_name)


def _strip_model_name(model: str, custom_llm_provider: Optional[str]) -> str:
    if custom_llm_provider and custom_llm_provider in ["bedrock", "bedrock_converse"]:
        stripped_bedrock_model = _get_base_bedrock_model(model_name=model)
        return stripped_bedrock_model
    elif custom_llm_provider and (
        custom_llm_provider == "vertex_ai" or custom_llm_provider == "gemini"
    ):
        strip_version = _strip_stable_vertex_version(model_name=model)
        return strip_version
    elif custom_llm_provider and (custom_llm_provider == "databricks"):
        strip_version = _strip_stable_vertex_version(model_name=model)
        return strip_version
    elif "ft:" in model:
        strip_finetune = _strip_openai_finetune_model_name(model_name=model)
        return strip_finetune
    else:
        return model

_model_cost_lowercase_map: Optional[Dict[str, str]] = None
_model_cost_mutation_generation: int = 0

def get_model_cost_mutation_generation() -> int:
    return _model_cost_mutation_generation

def _invalidate_model_cost_lowercase_map() -> None:
    global _model_cost_lowercase_map, _model_cost_mutation_generation
    _model_cost_lowercase_map = None
    _model_cost_mutation_generation += 1

    # Clear LRU caches that depend on model_cost data
    _cached_get_model_info.cache_clear()
    _cached_get_model_info_helper.cache_clear()


def _rebuild_model_cost_lowercase_map() -> Dict[str, str]:
    global _model_cost_lowercase_map
    _model_cost_lowercase_map = {k.lower(): k for k in config.model_cost}
    return _model_cost_lowercase_map


def _handle_stale_map_entry_rebuild(
    potential_key_lower: str,
) -> Optional[str]:
    global _model_cost_lowercase_map
    _model_cost_lowercase_map = _rebuild_model_cost_lowercase_map()
    matched_key = _model_cost_lowercase_map.get(potential_key_lower)
    if matched_key is not None and matched_key in config.model_cost:
        return matched_key
    return None

def _get_model_cost_key(potential_key: str) -> Optional[str]:
    global _model_cost_lowercase_map

    if potential_key in config.model_cost:
        return potential_key

    if _model_cost_lowercase_map is None:
        _model_cost_lowercase_map = _rebuild_model_cost_lowercase_map()

    potential_key_lower = potential_key.lower()
    matched_key = _model_cost_lowercase_map.get(potential_key_lower)

    if matched_key is not None and matched_key in config.model_cost:
        return matched_key

    # Rebuild map if stale entry detected (O(n) rebuild, but only when stale entry found)
    if matched_key is not None:
        matched_key = _handle_stale_map_entry_rebuild(potential_key_lower)
        if matched_key is not None:
            return matched_key

    return None

def _get_model_info_from_model_cost(key: str) -> dict:
    return config.model_cost[key]

def _check_provider_match(model_info: dict, custom_llm_provider: Optional[str]) -> bool:
    if custom_llm_provider and (
        model_info.get("litellm_provider") is not None
        and model_info["litellm_provider"] != custom_llm_provider
    ):
        if custom_llm_provider == "vertex_ai" and model_info[
            "litellm_provider"
        ].startswith("vertex_ai"):
            return True
        elif custom_llm_provider == "fireworks_ai" and model_info[
            "litellm_provider"
        ].startswith("fireworks_ai"):
            return True
        elif custom_llm_provider.startswith("bedrock") and model_info[
            "litellm_provider"
        ].startswith("bedrock"):
            return True
        elif (
            custom_llm_provider == "litellm_proxy"
        ):  # litellm_proxy is a special case, it's not a provider, it's a proxy for the provider
            return True
        elif custom_llm_provider == "azure_ai" and model_info["litellm_provider"] in (
            "azure",
            "openai",
        ):
            # Azure AI also works with azure models
            # as a last attempt if the model is not on Azure AI, Azure then fallback to OpenAI cost
            # tracking the cost is better than attributing 0 cost to it.
            return True
        elif custom_llm_provider == "github":
            # Allow github/<model> aliases to reuse existing provider metadata.
            return True
        else:
            return False

    return True


from typing_extensions import TypedDict

class PotentialModelNamesAndCustomLLMProvider(TypedDict):
    split_model: str
    combined_model_name: str
    stripped_model_name: str
    combined_stripped_model_name: str
    custom_llm_provider: str


def _get_potential_model_names(
    model: str, custom_llm_provider: Optional[str]
) -> PotentialModelNamesAndCustomLLMProvider:
    if custom_llm_provider is None:
        # Get custom_llm_provider
        try:
            get_llm_provider = getattr(sys.modules[__name__], "get_llm_provider")
            split_model, custom_llm_provider, _, _ = get_llm_provider(model=model)
        except Exception:
            split_model = model
        combined_model_name = model
        stripped_model_name = _strip_model_name(
            model=model, custom_llm_provider=custom_llm_provider
        )
        combined_stripped_model_name = stripped_model_name
    elif custom_llm_provider and model.startswith(
        custom_llm_provider + "/"
    ):  # handle case where custom_llm_provider is provided and model starts with custom_llm_provider
        split_model = model.split("/", 1)[1]
        combined_model_name = model
        stripped_model_name = _strip_model_name(
            model=split_model, custom_llm_provider=custom_llm_provider
        )
        combined_stripped_model_name = "{}/{}".format(
            custom_llm_provider, stripped_model_name
        )
    else:
        split_model = model
        combined_model_name = "{}/{}".format(custom_llm_provider, model)
        stripped_model_name = _strip_model_name(
            model=model, custom_llm_provider=custom_llm_provider
        )
        combined_stripped_model_name = "{}/{}".format(
            custom_llm_provider,
            stripped_model_name,
        )

    return PotentialModelNamesAndCustomLLMProvider(
        split_model=split_model,
        combined_model_name=combined_model_name,
        stripped_model_name=stripped_model_name,
        combined_stripped_model_name=combined_stripped_model_name,
        custom_llm_provider=cast(str, custom_llm_provider),
    )


def _get_max_position_embeddings(model_name: str) -> Optional[int]:
    # Construct the URL for the config.json file
    config_url = f"https://huggingface.co/{model_name}/raw/main/config.json"

    try:
        # Make the HTTP request to get the raw JSON file
        response = config.module_level_client.get(config_url)
        response.raise_for_status()  # Raise an exception for bad responses (4xx or 5xx)

        # Parse the JSON response
        config_json = response.json()

        # Extract and return the max_position_embeddings
        max_position_embeddings = config_json.get("max_position_embeddings")

        if max_position_embeddings is not None:
            return max_position_embeddings
        else:
            return None
    except Exception:
        return None


@lru_cache(maxsize=DEFAULT_MAX_LRU_CACHE_SIZE)
def _cached_get_model_info_helper(
    model: str,
    custom_llm_provider: Optional[str],
    api_base: Optional[str] = None,
) -> ModelInfoBase:
    """
    _get_model_info_helper wrapped with lru_cache

    Speed Optimization to hit high RPS
    """
    return _get_model_info_helper(
        model=model,
        custom_llm_provider=custom_llm_provider,
        api_base=api_base,
    )

def _is_potential_model_name_in_model_cost(
    potential_model_names: PotentialModelNamesAndCustomLLMProvider,
) -> bool:
    """
    Check if the potential model name is in the model cost (case-insensitive).
    """
    return any(
        _get_model_cost_key(str(potential_model_name)) is not None
        for potential_model_name in potential_model_names.values()
    )

def _get_model_info_helper(  # noqa: PLR0915
    model: str,
    custom_llm_provider: Optional[str] = None,
    api_base: Optional[str] = None,
    api_key: Optional[str] = None,
) -> ModelInfoBase:
    """
    Helper for 'get_model_info'. Separated out to avoid infinite loop caused by returning 'supported_openai_param's
    """
    try:
        azure_llms = {**config.azure_llms, **config.azure_embedding_models}
        if model in azure_llms:
            model = azure_llms[model]
        if custom_llm_provider is not None and custom_llm_provider == "vertex_ai_beta":
            custom_llm_provider = "vertex_ai"
        if custom_llm_provider is not None and custom_llm_provider == "vertex_ai":
            if "meta/" + model in config.vertex_llama3_models:
                model = "meta/" + model
            elif model + "@latest" in config.vertex_mistral_models:
                model = model + "@latest"
            elif model + "@latest" in config.vertex_ai_ai21_models:
                model = model + "@latest"
        ##########################
        potential_model_names = _get_potential_model_names(
            model=model, custom_llm_provider=custom_llm_provider
        )

        log.debug(
            f"checking potential_model_names in litellm.model_cost: {potential_model_names}"
        )

        combined_model_name = potential_model_names["combined_model_name"]
        stripped_model_name = potential_model_names["stripped_model_name"]
        combined_stripped_model_name = potential_model_names[
            "combined_stripped_model_name"
        ]
        split_model = potential_model_names["split_model"]
        custom_llm_provider = potential_model_names["custom_llm_provider"]
        #########################
        provider_config: Optional[BaseLLMModelInfo] = None
        if custom_llm_provider and custom_llm_provider in LlmProvidersSet:
            provider_config = ProviderConfigManager.get_provider_model_info(
                model=model, provider=LlmProviders(custom_llm_provider)
            )
        if provider_config is not None:
            provider_get_model_info = getattr(provider_config, "get_model_info", None)
            if callable(provider_get_model_info):
                try:
                    provider_model_info = provider_get_model_info(
                        model=model,
                        api_base=api_base,
                        api_key=api_key,
                    )
                    if provider_model_info is not None:
                        return provider_model_info
                except Exception as e:
                    log.warning(
                        "Could not get dynamic model info for model=%s, provider=%s; "
                        "falling back to the static cost map: %s",
                        model,
                        custom_llm_provider,
                        e,
                    )

        if custom_llm_provider == "huggingface":
            max_tokens = _get_max_position_embeddings(model_name=model)
            return ModelInfoBase(
                key=model,
                max_tokens=max_tokens,  # type: ignore
                max_input_tokens=None,
                max_output_tokens=None,
                input_cost_per_token=0,
                output_cost_per_token=0,
                litellm_provider="huggingface",
                mode="chat",
                supports_system_messages=None,
                supports_response_schema=None,
                supports_function_calling=None,
                supports_tool_choice=None,
                supports_assistant_prefill=None,
                supports_prompt_caching=None,
                supports_computer_use=None,
                supports_pdf_input=None,
            )
        else:
            """
            Check if: (in order of specificity)
            1. 'custom_llm_provider/model' in litellm.model_cost. Checks "groq/llama3-8b-8192" if model="llama3-8b-8192" and custom_llm_provider="groq"
            2. 'model' in litellm.model_cost. Checks "gemini-1.5-pro-002" in  litellm.model_cost if model="gemini-1.5-pro-002" and custom_llm_provider=None
            3. 'combined_stripped_model_name' in litellm.model_cost. Checks if 'gemini/gemini-1.5-flash' in model map, if 'gemini/gemini-1.5-flash-001' given.
            4. 'stripped_model_name' in litellm.model_cost. Checks if 'ft:gpt-3.5-turbo' in model map, if 'ft:gpt-3.5-turbo:my-org:custom_suffix:id' given.
            5. 'split_model' in litellm.model_cost. Checks "llama3-8b-8192" in litellm.model_cost if model="groq/llama3-8b-8192"
            """

            _model_info: Optional[Dict[str, Any]] = None
            key: Optional[str] = None

            # Use case-insensitive lookup for all model name checks
            _matched_key = _get_model_cost_key(combined_model_name)
            if _matched_key is not None:
                key = _matched_key
                _model_info = _get_model_info_from_model_cost(key=cast(str, key))
                if not _check_provider_match(
                    model_info=_model_info, custom_llm_provider=custom_llm_provider
                ):
                    _model_info = None
            if _model_info is None:
                _matched_key = _get_model_cost_key(model)
                if _matched_key is not None:
                    key = _matched_key
                    _model_info = _get_model_info_from_model_cost(key=cast(str, key))
                    if not _check_provider_match(
                        model_info=_model_info, custom_llm_provider=custom_llm_provider
                    ):
                        _model_info = None
            if _model_info is None:
                _matched_key = _get_model_cost_key(combined_stripped_model_name)
                if _matched_key is not None:
                    key = _matched_key
                    _model_info = _get_model_info_from_model_cost(key=cast(str, key))
                    if not _check_provider_match(
                        model_info=_model_info, custom_llm_provider=custom_llm_provider
                    ):
                        _model_info = None
            if _model_info is None:
                _matched_key = _get_model_cost_key(stripped_model_name)
                if _matched_key is not None:
                    key = _matched_key
                    _model_info = _get_model_info_from_model_cost(key=cast(str, key))
                    if not _check_provider_match(
                        model_info=_model_info, custom_llm_provider=custom_llm_provider
                    ):
                        _model_info = None
            if _model_info is None:
                _matched_key = _get_model_cost_key(split_model)
                if _matched_key is not None:
                    key = _matched_key
                    _model_info = _get_model_info_from_model_cost(key=cast(str, key))
                    if not _check_provider_match(
                        model_info=_model_info, custom_llm_provider=custom_llm_provider
                    ):
                        _model_info = None

            if _model_info is None or key is None:
                raise ValueError(
                    "This model isn't mapped yet. Add it here - https://github.com/BerriAI/litellm/blob/main/model_prices_and_context_window.json"
                )

            _input_cost_per_token: Optional[float] = _model_info.get(
                "input_cost_per_token"
            )
            if _input_cost_per_token is None:
                # default value to 0, be noisy about this
                log.debug(
                    "model={}, custom_llm_provider={} has no input_cost_per_token in model_cost_map. Defaulting to 0.".format(
                        model, custom_llm_provider
                    )
                )
                _input_cost_per_token = 0

            _output_cost_per_token: Optional[float] = _model_info.get(
                "output_cost_per_token"
            )
            if _output_cost_per_token is None:
                # default value to 0, be noisy about this
                log.debug(
                    "model={}, custom_llm_provider={} has no output_cost_per_token in model_cost_map. Defaulting to 0.".format(
                        model, custom_llm_provider
                    )
                )
                _output_cost_per_token = 0

            return ModelInfoBase(
                key=key,
                max_tokens=_model_info.get("max_tokens", None),
                max_input_tokens=_model_info.get("max_input_tokens", None),
                max_output_tokens=_model_info.get("max_output_tokens", None),
                input_cost_per_token=_input_cost_per_token,
                input_cost_per_token_flex=_model_info.get(
                    "input_cost_per_token_flex", None
                ),
                input_cost_per_token_priority=_model_info.get(
                    "input_cost_per_token_priority", None
                ),
                cache_creation_input_token_cost=_model_info.get(
                    "cache_creation_input_token_cost", None
                ),
                cache_creation_input_token_cost_above_200k_tokens=_model_info.get(
                    "cache_creation_input_token_cost_above_200k_tokens", None
                ),
                cache_read_input_token_cost=_model_info.get(
                    "cache_read_input_token_cost", None
                ),
                cache_read_input_token_cost_above_200k_tokens=_model_info.get(
                    "cache_read_input_token_cost_above_200k_tokens", None
                ),
                cache_read_input_token_cost_above_272k_tokens=_model_info.get(
                    "cache_read_input_token_cost_above_272k_tokens", None
                ),
                cache_read_input_token_cost_flex=_model_info.get(
                    "cache_read_input_token_cost_flex", None
                ),
                cache_read_input_token_cost_priority=_model_info.get(
                    "cache_read_input_token_cost_priority", None
                ),
                cache_creation_input_token_cost_above_1hr=_model_info.get(
                    "cache_creation_input_token_cost_above_1hr", None
                ),
                input_cost_per_character=_model_info.get(
                    "input_cost_per_character", None
                ),
                input_cost_per_token_above_128k_tokens=_model_info.get(
                    "input_cost_per_token_above_128k_tokens", None
                ),
                input_cost_per_token_above_200k_tokens=_model_info.get(
                    "input_cost_per_token_above_200k_tokens", None
                ),
                input_cost_per_token_above_272k_tokens=_model_info.get(
                    "input_cost_per_token_above_272k_tokens", None
                ),
                input_cost_per_query=_model_info.get("input_cost_per_query", None),
                input_cost_per_second=_model_info.get("input_cost_per_second", None),
                input_cost_per_audio_token=_model_info.get(
                    "input_cost_per_audio_token", None
                ),
                input_cost_per_image_token=_model_info.get(
                    "input_cost_per_image_token", None
                ),
                input_cost_per_image=_model_info.get("input_cost_per_image", None),
                input_cost_per_audio_per_second=_model_info.get(
                    "input_cost_per_audio_per_second", None
                ),
                input_cost_per_video_per_second=_model_info.get(
                    "input_cost_per_video_per_second", None
                ),
                input_cost_per_token_batches=_model_info.get(
                    "input_cost_per_token_batches"
                ),
                output_cost_per_token_batches=_model_info.get(
                    "output_cost_per_token_batches"
                ),
                output_cost_per_token=_output_cost_per_token,
                output_cost_per_token_flex=_model_info.get(
                    "output_cost_per_token_flex", None
                ),
                output_cost_per_token_priority=_model_info.get(
                    "output_cost_per_token_priority", None
                ),
                regional_processing_uplift_multiplier_eu=_model_info.get(
                    "regional_processing_uplift_multiplier_eu", None
                ),
                regional_processing_uplift_multiplier_us=_model_info.get(
                    "regional_processing_uplift_multiplier_us", None
                ),
                output_cost_per_audio_token=_model_info.get(
                    "output_cost_per_audio_token", None
                ),
                output_cost_per_character=_model_info.get(
                    "output_cost_per_character", None
                ),
                output_cost_per_reasoning_token=_model_info.get(
                    "output_cost_per_reasoning_token", None
                ),
                output_cost_per_token_above_128k_tokens=_model_info.get(
                    "output_cost_per_token_above_128k_tokens", None
                ),
                output_cost_per_character_above_128k_tokens=_model_info.get(
                    "output_cost_per_character_above_128k_tokens", None
                ),
                output_cost_per_token_above_200k_tokens=_model_info.get(
                    "output_cost_per_token_above_200k_tokens", None
                ),
                output_cost_per_token_above_272k_tokens=_model_info.get(
                    "output_cost_per_token_above_272k_tokens", None
                ),
                output_cost_per_second=_model_info.get("output_cost_per_second", None),
                output_cost_per_second_1080p=_model_info.get(
                    "output_cost_per_second_1080p", None
                ),
                output_cost_per_video_per_second=_model_info.get(
                    "output_cost_per_video_per_second", None
                ),
                output_cost_per_image=_model_info.get("output_cost_per_image", None),
                output_cost_per_image_token=_model_info.get(
                    "output_cost_per_image_token", None
                ),
                output_vector_size=_model_info.get("output_vector_size", None),
                citation_cost_per_token=_model_info.get(
                    "citation_cost_per_token", None
                ),
                tiered_pricing=_model_info.get("tiered_pricing", None),
                litellm_provider=_model_info.get(
                    "litellm_provider", custom_llm_provider
                ),
                mode=_model_info.get("mode"),  # type: ignore
                supports_system_messages=_model_info.get(
                    "supports_system_messages", None
                ),
                supports_response_schema=_model_info.get(
                    "supports_response_schema", None
                ),
                supports_vision=_model_info.get("supports_vision", None),
                supports_function_calling=_model_info.get(
                    "supports_function_calling", None
                ),
                supports_tool_choice=_model_info.get("supports_tool_choice", None),
                supports_assistant_prefill=_model_info.get(
                    "supports_assistant_prefill", None
                ),
                supports_prompt_caching=_model_info.get(
                    "supports_prompt_caching", None
                ),
                supports_audio_input=_model_info.get("supports_audio_input", None),
                supports_audio_output=_model_info.get("supports_audio_output", None),
                supports_pdf_input=_model_info.get("supports_pdf_input", None),
                supports_embedding_image_input=_model_info.get(
                    "supports_embedding_image_input", None
                ),
                supports_native_streaming=_model_info.get(
                    "supports_native_streaming", None
                ),
                supports_native_structured_output=_model_info.get(
                    "supports_native_structured_output", None
                ),
                supports_web_search=_model_info.get("supports_web_search", None),
                supports_url_context=_model_info.get("supports_url_context", None),
                supports_reasoning=_model_info.get("supports_reasoning", None),
                supports_none_reasoning_effort=_model_info.get(
                    "supports_none_reasoning_effort", None
                ),
                supports_minimal_reasoning_effort=_model_info.get(
                    "supports_minimal_reasoning_effort", None
                ),
                supports_low_reasoning_effort=_model_info.get(
                    "supports_low_reasoning_effort", None
                ),
                supports_xhigh_reasoning_effort=_model_info.get(
                    "supports_xhigh_reasoning_effort", None
                ),
                supports_max_reasoning_effort=_model_info.get(
                    "supports_max_reasoning_effort", None
                ),
                bedrock_output_config_effort_ceiling=_model_info.get(
                    "bedrock_output_config_effort_ceiling", None
                ),
                supports_computer_use=_model_info.get("supports_computer_use", None),
                search_context_cost_per_query=_model_info.get(
                    "search_context_cost_per_query", None
                ),
                tpm=_model_info.get("tpm", None),
                rpm=_model_info.get("rpm", None),
                ocr_cost_per_page=_model_info.get("ocr_cost_per_page", None),
                ocr_cost_per_credit=_model_info.get("ocr_cost_per_credit", None),
                annotation_cost_per_page=_model_info.get(
                    "annotation_cost_per_page", None
                ),
                provider_specific_entry=_model_info.get(
                    "provider_specific_entry", None
                ),
                uses_embed_content=_model_info.get("uses_embed_content", None),
                supports_image_size=_model_info.get("supports_image_size", None),
            )
    except Exception as e:
        log.debug(f"Error getting model info: {e}")
        raise Exception(
            "This model isn't mapped yet. model={}, custom_llm_provider={}. Add it here - https://github.com/BerriAI/litellm/blob/main/model_prices_and_context_window.json.".format(
                model, custom_llm_provider
            )
        )

def json_schema_type(python_type_name: str):
    """Converts standard python types to json schema types

    Parameters
    ----------
    python_type_name : str
        __name__ of type

    Returns
    -------
    str
        a standard JSON schema type, "string" if not recognized.
    """
    python_to_json_schema_types = {
        str.__name__: "string",
        int.__name__: "integer",
        float.__name__: "number",
        bool.__name__: "boolean",
        list.__name__: "array",
        dict.__name__: "object",
        "NoneType": "null",
    }

    return python_to_json_schema_types.get(python_type_name, "string")

def function_to_dict(input_function) -> dict:  # noqa: C901
    try:
        import inspect
        from ast import literal_eval

        from numpydoc.docscrape import NumpyDocString
    except Exception as e:
        raise e

    name = input_function.__name__
    docstring = inspect.getdoc(input_function)
    numpydoc = NumpyDocString(docstring)
    description = "\n".join([s.strip() for s in numpydoc["Summary"]])

    # Get function parameters and their types from annotations and docstring
    parameters = {}
    required_params = []
    param_info = inspect.signature(input_function).parameters

    for param_name, param in param_info.items():
        if hasattr(param, "annotation"):
            param_type = json_schema_type(param.annotation.__name__)
        else:
            param_type = None
        param_description = None
        param_enum = None

        # Try to extract param description from docstring using numpydoc
        for param_data in numpydoc["Parameters"]:
            if param_data.name == param_name:
                if hasattr(param_data, "type"):
                    # replace type from docstring rather than annotation
                    param_type = param_data.type
                    if "optional" in param_type:
                        param_type = param_type.split(",")[0]
                    elif "{" in param_type:
                        # may represent a set of acceptable values
                        # translating as enum for function calling
                        try:
                            param_enum = str(list(literal_eval(param_type)))
                            param_type = "string"
                        except Exception:
                            pass
                    param_type = json_schema_type(param_type)
                param_description = "\n".join([s.strip() for s in param_data.desc])

        param_dict = {
            "type": param_type,
            "description": param_description,
            "enum": param_enum,
        }

        parameters[param_name] = dict(
            [(k, v) for k, v in param_dict.items() if isinstance(v, str)]
        )

        # Check if the parameter has no default value (i.e., it's required)
        if param.default == param.empty:
            required_params.append(param_name)

    # Create the dictionary
    result = {
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": parameters,
        },
    }

    # Add "required" key if there are required parameters
    if required_params:
        result["parameters"]["required"] = required_params

    return result

def acreate(*args, **kwargs):  ## Thin client to handle the acreate langchain call
    return config.acompletion(*args, **kwargs)

def valid_model(model):
    try:
        # for a given model name, check if the user has the right permissions to access the model
        if (
            model in config.open_ai_chat_completion_models
            or model in config.open_ai_text_completion_models
        ):
            openai.models.retrieve(model)
        else:
            messages = [{"role": "user", "content": "Hello World"}]
            config.completion(model=model, messages=messages)
    except Exception:
        raise BadRequestError(message="", model=model, llm_provider="")

def check_valid_key(model: str, api_key: str):
    messages = [{"role": "user", "content": "Hey, how's it going?"}]
    try:
        config.completion(
            model=model, messages=messages, api_key=api_key, max_tokens=10
        )
        return True
    except AuthenticationError:
        return False
    except Exception:
        return False

def register_prompt_template(
    model: str,
    roles: dict = {},
    initial_prompt_value: str = "",
    final_prompt_value: str = "",
    tokenizer_config: dict = {},
):
    complete_model = model
    potential_models = [complete_model]
    try:
        get_llm_provider = getattr(sys.modules[__name__], "get_llm_provider")
        model = get_llm_provider(model=model)[0]
        potential_models.append(model)
    except Exception:
        pass
    if tokenizer_config:
        for m in potential_models:
            config.known_tokenizer_config[m] = {
                "tokenizer": tokenizer_config,
                "status": "success",
            }
    else:
        for m in potential_models:
            config.custom_prompt_dict[m] = {
                "roles": roles,
                "initial_prompt_value": initial_prompt_value,
                "final_prompt_value": final_prompt_value,
            }

    return config.custom_prompt_dict

class TextCompletionStreamWrapper:
    def __init__(
        self,
        completion_stream,
        model,
        stream_options: Optional[dict] = None,
        custom_llm_provider: Optional[str] = None,
    ):
        self.completion_stream = completion_stream
        self.model = model
        self.stream_options = stream_options
        self.custom_llm_provider = custom_llm_provider

    def __iter__(self):
        return self

    def __aiter__(self):
        return self

    def convert_to_text_completion_object(self, chunk: ModelResponse):
        try:
            response = TextCompletionResponse()
            response["id"] = chunk.get("id", None)
            response["object"] = "text_completion"
            response["created"] = chunk.get("created", None)
            response["model"] = chunk.get("model", None)
            text_choices = TextChoices()
            if isinstance(
                chunk, Choices
            ):  # chunk should always be of type StreamingChoices
                raise Exception
            delta = chunk["choices"][0]["delta"]
            text_choices["text"] = delta["content"]
            text_choices["reasoning_content"] = delta.get("reasoning_content")
            text_choices["index"] = chunk["choices"][0]["index"]
            text_choices["finish_reason"] = chunk["choices"][0]["finish_reason"]
            response["choices"] = [text_choices]

            # only pass usage when stream_options["include_usage"] is True
            if (
                self.stream_options
                and self.stream_options.get("include_usage", False) is True
            ):
                response["usage"] = chunk.get("usage", None)

            return response
        except Exception as e:
            raise Exception(
                f"Error occurred converting to text completion object - chunk: {chunk}; Error: {str(e)}"
            )

    def __next__(self):
        # model_response = ModelResponse(stream=True, model=self.model)
        TextCompletionResponse()
        try:
            for chunk in self.completion_stream:
                if chunk == "None" or chunk is None:
                    raise Exception
                processed_chunk = self.convert_to_text_completion_object(chunk=chunk)
                return processed_chunk
            raise StopIteration
        except StopIteration:
            raise StopIteration
        except Exception as e:
            exception_type = getattr(sys.modules[__name__], "exception_type")
            raise exception_type(
                model=self.model,
                custom_llm_provider=self.custom_llm_provider or "",
                original_exception=e,
                completion_kwargs={},
                extra_kwargs={},
            )

    async def __anext__(self):
        try:
            async for chunk in self.completion_stream:
                if chunk == "None" or chunk is None:
                    raise Exception
                processed_chunk = self.convert_to_text_completion_object(chunk=chunk)
                return processed_chunk
            raise StopIteration
        except StopIteration:
            raise StopAsyncIteration


def mock_completion_streaming_obj(
    model_response, mock_response, model, n: Optional[int] = None
):
    if isinstance(mock_response, MockException):
        raise mock_response
    if isinstance(mock_response, ModelResponseStream):
        yield mock_response
        return
    for i in range(0, len(mock_response), 3):
        completion_obj = Delta(role="assistant", content=mock_response[i : i + 3])
        if n is None:
            model_response.choices[0].delta = completion_obj
        else:
            _all_choices = []
            for j in range(n):
                _streaming_choice = config.utils.StreamingChoices(
                    index=j,
                    delta=config.utils.Delta(
                        role="assistant", content=mock_response[i : i + 3]
                    ),
                )
                _all_choices.append(_streaming_choice)
            model_response.choices = _all_choices
        yield model_response


async def async_mock_completion_streaming_obj(
    model_response,
    mock_response: Union[str, "MockException", ModelResponseStream],
    model,
    n: Optional[int] = None,
):
    if isinstance(mock_response, config.MockException):
        raise mock_response
    if isinstance(mock_response, ModelResponseStream):
        yield mock_response
        return
    for i in range(0, len(mock_response), 3):
        completion_obj = Delta(role="assistant", content=mock_response[i : i + 3])
        if n is None:
            model_response.choices[0].delta = completion_obj
        else:
            _all_choices = []
            for j in range(n):
                _streaming_choice = config.utils.StreamingChoices(
                    index=j,
                    delta=config.utils.Delta(
                        role="assistant", content=mock_response[i : i + 3]
                    ),
                )
                _all_choices.append(_streaming_choice)
            model_response.choices = _all_choices
        yield model_response


########## Reading Config File ############################
def read_config_args(config_path) -> dict:
    try:
        import os

        os.getcwd()
        with open(config_path, "r") as config_file:
            config = json.load(config_file)

        # read keys/ values from config file and return them
        return config
    except Exception as e:
        raise e


########## experimental completion variants ############################


def process_system_message(system_message, max_tokens, model):
    system_message_event = {"role": "system", "content": system_message}
    system_message_tokens = get_token_count([system_message_event], model)

    if system_message_tokens > max_tokens:
        new_system_message = shorten_message_to_fit_limit(
            system_message_event, max_tokens, model
        )
        system_message_tokens = get_token_count([new_system_message], model)

    return system_message_event, max_tokens - system_message_tokens

def process_messages(messages, max_tokens, model):
    # Process messages from older to more recent
    messages = messages[::-1]
    final_messages = []
    log.debug(
        f"calling process_messages with messages: {messages}, max_tokens: {max_tokens}, model: {model}"
    )
    for message in messages:
        log.debug(f"processing final_messages: {final_messages}")
        used_tokens = get_token_count(final_messages, model)
        available_tokens = max_tokens - used_tokens
        log.debug(
            f"used_tokens: {used_tokens}, available_tokens: {available_tokens}"
        )
        if available_tokens <= 3:
            break

        final_messages = attempt_message_addition(
            final_messages=final_messages,
            message=message,
            available_tokens=available_tokens,
            max_tokens=max_tokens,
            model=model,
        )
        log.debug(
            f"final_messages after attempt_message_addition: {final_messages}"
        )
    log.debug(f"Final messages: {final_messages}")
    return final_messages


def attempt_message_addition(
    final_messages, message, available_tokens, max_tokens, model
):
    temp_messages = [message] + final_messages
    temp_message_tokens = get_token_count(messages=temp_messages, model=model)
    log.debug(
        f"temp_message_tokens: {temp_message_tokens}, max_tokens: {max_tokens}"
    )
    if temp_message_tokens <= max_tokens:
        return temp_messages

    # if temp_message_tokens > max_tokens, try shortening temp_messages
    elif "function_call" not in message:
        log.debug("attempting to shorten message to fit limit")
        # fit updated_message to be within temp_message_tokens - max_tokens (aka the amount temp_message_tokens is greate than max_tokens)
        updated_message = shorten_message_to_fit_limit(message, available_tokens, model)
        if can_add_message(updated_message, final_messages, max_tokens, model):
            log.debug(
                "can add message, returning [updated_message] + final_messages"
            )
            return [updated_message] + final_messages
        else:
            log.debug("cannot add message, returning final_messages")
    return final_messages


def can_add_message(message, messages, max_tokens, model):
    if get_token_count(messages + [message], model) <= max_tokens:
        return True
    return False


def get_token_count(messages, model):
    return token_counter(model=model, messages=messages)


def shorten_message_to_fit_limit(
    message, tokens_needed, model: Optional[str], raise_error_on_max_limit: bool = False
):
    """
    Shorten a message to fit within a token limit by removing characters from the middle.

    Args:
        message: The message to shorten
        tokens_needed: The maximum number of tokens allowed
        model: The model being used (optional)
        raise_error_on_max_limit: If True, raises an error when max attempts reached. If False, returns final trimmed content.
    """

    # For OpenAI models, even blank messages cost 7 token,
    # and if the buffer is less than 3, the while loop will never end,
    # hence the value 10.
    if model is not None and "gpt" in model and tokens_needed <= 10:
        return message

    content = message["content"]
    attempts = 0

    log.debug(f"content: {content}")

    while attempts < MAX_TOKEN_TRIMMING_ATTEMPTS:
        log.debug(f"getting token count for message: {message}")
        total_tokens = get_token_count([message], model)
        log.debug(
            f"total_tokens: {total_tokens}, tokens_needed: {tokens_needed}"
        )

        if total_tokens <= tokens_needed:
            break

        ratio = (tokens_needed) / total_tokens

        new_length = int(len(content) * ratio) - 1
        new_length = max(0, new_length)

        half_length = new_length // 2
        left_half = content[:half_length]
        right_half = content[-half_length:]

        trimmed_content = left_half + ".." + right_half
        message["content"] = trimmed_content
        log.debug(f"trimmed_content: {trimmed_content}")
        content = trimmed_content
        attempts += 1

    if attempts >= MAX_TOKEN_TRIMMING_ATTEMPTS and raise_error_on_max_limit:
        raise Exception(
            f"Failed to trim message to fit within {tokens_needed} tokens after {MAX_TOKEN_TRIMMING_ATTEMPTS} attempts"
        )

    return message

class AvailableModelsCache(InMemoryCache):
    def __init__(self, ttl_seconds: int = 300, max_size: int = 1000):
        super().__init__(ttl_seconds, max_size)
        self._env_hash: Optional[str] = None

    def _get_env_hash(self) -> str:
        """Create a hash of relevant environment variables"""
        env_vars = {
            k: v
            for k, v in os.environ.items()
            if k.startswith(("OPENAI", "ANTHROPIC", "AZURE", "AWS"))
        }
        return str(hash(frozenset(env_vars.items())))

    def _check_env_changed(self) -> bool:
        """Check if environment variables have changed"""
        current_hash = self._get_env_hash()
        if self._env_hash is None:
            self._env_hash = current_hash
            return True
        return current_hash != self._env_hash

    def _get_cache_key(
        self,
        custom_llm_provider: Optional[str],
        litellm_params: Optional[LiteLLM_Params],
    ) -> str:
        valid_str = ""

        if litellm_params is not None:
            valid_str = litellm_params.model_dump_json()
        if custom_llm_provider is not None:
            valid_str = f"{custom_llm_provider}:{valid_str}"
        return hashlib.sha256(valid_str.encode()).hexdigest()

    def get_cached_model_info(
        self,
        custom_llm_provider: Optional[str] = None,
        litellm_params: Optional[LiteLLM_Params] = None,
    ) -> Optional[List[str]]:
        """Get cached model info"""
        # Check if environment has changed
        if litellm_params is None and self._check_env_changed():
            self.cache_dict.clear()
            return None

        cache_key = self._get_cache_key(custom_llm_provider, litellm_params)

        result = cast(Optional[List[str]], self.get_cache(cache_key))

        if result is not None:
            return copy.deepcopy(result)
        return result

    def set_cached_model_info(
        self,
        custom_llm_provider: str,
        litellm_params: Optional[LiteLLM_Params],
        available_models: List[str],
    ):
        """Set cached model info"""
        cache_key = self._get_cache_key(custom_llm_provider, litellm_params)
        self.set_cache(cache_key, copy.deepcopy(available_models))


# Global cache instance
_model_cache = AvailableModelsCache()

def _infer_valid_provider_from_env_vars(
    custom_llm_provider: Optional[str] = None,
) -> List[str]:
    valid_providers: List[str] = []
    environ_keys = os.environ.keys()
    for provider in config.provider_list:
        if custom_llm_provider and provider != custom_llm_provider:
            continue

        # edge case litellm has together_ai as a provider, it should be togetherai
        env_provider_1 = provider.replace("_", "")
        env_provider_2 = provider

        # litellm standardizes expected provider keys to
        # PROVIDER_API_KEY. Example: OPENAI_API_KEY, COHERE_API_KEY
        expected_provider_key_1 = f"{env_provider_1.upper()}_API_KEY"
        expected_provider_key_2 = f"{env_provider_2.upper()}_API_KEY"
        if (
            expected_provider_key_1 in environ_keys
            or expected_provider_key_2 in environ_keys
        ):
            # key is set
            valid_providers.append(provider)

    return valid_providers

def _get_valid_models_from_provider_api(
    provider_config: BaseLLMModelInfo,
    custom_llm_provider: str,
    litellm_params: Optional[LiteLLM_Params] = None,
) -> List[str]:
    try:
        cached_result = _model_cache.get_cached_model_info(
            custom_llm_provider, litellm_params
        )

        if cached_result is not None:
            return cached_result
        models = provider_config.get_models(
            api_key=litellm_params.api_key if litellm_params is not None else None,
            api_base=litellm_params.api_base if litellm_params is not None else None,
        )

        _model_cache.set_cached_model_info(custom_llm_provider, litellm_params, models)
        return models
    except Exception as e:
        log.warning(f"Error getting valid models: {e}")
        return []

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


def get_logging_id(start_time, response_obj):
    try:
        response_id = (
            "time-" + start_time.strftime("%H-%M-%S-%f") + "_" + response_obj.get("id")
        )
        return response_id
    except Exception:
        return None


def _get_base_model_from_metadata(model_call_details=None):
    if model_call_details is None:
        return None
    litellm_params = model_call_details.get("litellm_params", {})
    if litellm_params is not None:
        _base_model = litellm_params.get("base_model", None)
        if _base_model is not None:
            return _base_model
        metadata = litellm_params.get("metadata") or {}

        _get_base_model_from_litellm_call_metadata = getattr(
            sys.modules[__name__], "_get_base_model_from_litellm_call_metadata"
        )
        base_model_from_metadata = _get_base_model_from_litellm_call_metadata(
            metadata=metadata
        )
        if base_model_from_metadata is not None:
            return base_model_from_metadata

        # Also check litellm_metadata (used by Responses API and other generic API calls)
        litellm_metadata = litellm_params.get("litellm_metadata", {})
        _get_base_model_from_litellm_call_metadata = getattr(
            sys.modules[__name__], "_get_base_model_from_litellm_call_metadata"
        )
        return _get_base_model_from_litellm_call_metadata(metadata=litellm_metadata)
    return None

class ModelResponseIterator:
    def __init__(self, model_response: ModelResponse, convert_to_delta: bool = False):
        if convert_to_delta is True:
            _stream_response = ModelResponseStream()
            _stream_response.choices[0].delta.content = model_response.choices[0].message.content  # type: ignore
            self.model_response: Union[ModelResponse, ModelResponseStream] = (
                _stream_response
            )
        else:
            self.model_response = model_response
        self.is_done = False

    # Sync iterator
    def __iter__(self):
        return self

    def __next__(self):
        if self.is_done:
            raise StopIteration
        self.is_done = True
        return self.model_response

    # Async iterator
    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.is_done:
            raise StopAsyncIteration
        self.is_done = True
        return self.model_response

class ModelResponseListIterator:
    def __init__(self, model_responses, delay: Optional[float] = None):
        self.model_responses = model_responses
        self.index = 0
        self.delay = delay

    # Sync iterator
    def __iter__(self):
        return self

    def __next__(self):
        if self.index >= len(self.model_responses):
            raise StopIteration
        model_response = self.model_responses[self.index]
        self.index += 1
        if self.delay:
            time.sleep(self.delay)
        return model_response

    # Async iterator
    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.index >= len(self.model_responses):
            raise StopAsyncIteration
        model_response = self.model_responses[self.index]
        self.index += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        return model_response

class CustomModelResponseIterator(Iterable):
    def __init__(self) -> None:
        super().__init__()


def is_cached_message(message: AllMessageValues) -> bool:
    # Check if context caching is disabled globally
    if config.disable_anthropic_gemini_context_caching_transform is True:
        return False

    # Check message-level cache_control (set by cache_control_injection_points hook for string content)
    message_level_cache_control = message.get("cache_control")
    if (
        message_level_cache_control is not None
        and isinstance(message_level_cache_control, dict)
        and message_level_cache_control.get("type") == "ephemeral"
    ):
        return True

    if "content" not in message:
        return False

    content = message["content"]

    # Handle non-list content types (None, str, etc.)
    if not isinstance(content, list):
        return False

    for content_item in content:
        # Ensure content_item is a dictionary before accessing keys
        if not isinstance(content_item, dict):
            continue

        cache_control = content_item.get("cache_control")
        if (
            content_item.get("type") == "text"
            and cache_control is not None
            and isinstance(cache_control, dict)
            and cache_control.get("type") == "ephemeral"
        ):
            return True

    return False

def has_tool_call_blocks(messages: List[AllMessageValues]) -> bool:
    for message in messages:
        if message.get("tool_calls") is not None:
            return True
    return False

def any_assistant_message_has_thinking_blocks(
    messages: List[AllMessageValues],
) -> bool:
    for message in messages:
        if message.get("role") == "assistant":
            thinking_blocks = message.get("thinking_blocks")
            if thinking_blocks is not None and (
                not hasattr(thinking_blocks, "__len__") or len(thinking_blocks) > 0
            ):
                return True
    return False

def last_assistant_with_tool_calls_has_no_thinking_blocks(
    messages: List[AllMessageValues],
) -> bool:
    # Find the last assistant message with tool_calls
    last_assistant_with_tools = None
    for message in messages:
        if message.get("role") == "assistant" and message.get("tool_calls") is not None:
            last_assistant_with_tools = message

    if last_assistant_with_tools is None:
        return False

    # Check if it has thinking_blocks
    thinking_blocks = last_assistant_with_tools.get("thinking_blocks")
    return thinking_blocks is None or (
        hasattr(thinking_blocks, "__len__") and len(thinking_blocks) == 0
    )


def add_dummy_tool(custom_llm_provider: str) -> List[ChatCompletionToolParam]:
    return [
        ChatCompletionToolParam(
            type="function",
            function=ChatCompletionToolParamFunctionChunk(
                name="dummy_tool",
                description="This is a dummy tool call",  # provided to satisfy bedrock constraint.
                parameters={
                    "type": "object",
                    "properties": {},
                },
            ),
        )
    ]

def convert_to_dict(message: Union[BaseModel, dict]) -> dict:
    if isinstance(message, BaseModel):
        return message.model_dump(exclude_none=True)  # type: ignore
    elif isinstance(message, dict):
        return message
    else:
        raise TypeError(
            f"Invalid message type: {type(message)}. Expected dict or Pydantic model."
        )

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
        model_info = config.model_cost.get(model_key)
        if model_info is not None:
            return model_info

    bundled_model_cost = _get_bundled_model_cost_map()
    for model_key in candidate_keys:
        model_info = bundled_model_cost.get(model_key)
        if model_info is not None:
            return model_info
    return {}

def get_end_user_id_for_cost_tracking(
    litellm_params: dict,
    service_type: Literal["litellm_logging", "prometheus"] = "litellm_logging",
) -> Optional[str]:
    """
    Used for enforcing `disable_end_user_cost_tracking` param.

    service_type: "litellm_logging" or "prometheus" - used to allow prometheus only disable cost tracking.
    """
    get_litellm_metadata_from_kwargs = getattr(
        sys.modules[__name__], "get_litellm_metadata_from_kwargs"
    )
    _metadata = cast(
        dict, get_litellm_metadata_from_kwargs(dict(litellm_params=litellm_params))
    )

    end_user_id = cast(
        Optional[str],
        litellm_params.get("user_api_key_end_user_id")
        or _metadata.get("user_api_key_end_user_id"),
    )
    if config.disable_end_user_cost_tracking:
        return None

    #######################################
    # By default we don't track end_user on prometheus since we don't want to increase cardinality
    # by default litellm.enable_end_user_cost_tracking_prometheus_only is None, so we don't track end_user on prometheus
    #######################################
    if service_type == "prometheus":
        if config.enable_end_user_cost_tracking_prometheus_only is not True:
            return None
    return end_user_id


def should_use_cohere_v1_client(
    api_base: Optional[str], present_version_params: List[str]
):
    if not api_base:
        return False
    uses_v1_params = ("max_chunks_per_doc" in present_version_params) and (
        "max_tokens_per_doc" not in present_version_params
    )
    return api_base.endswith("/v1/rerank") or (
        uses_v1_params and not api_base.endswith("/v2/rerank")
    )


def is_prompt_caching_valid_prompt(
    model: str,
    messages: Optional[List[AllMessageValues]],
    tools: Optional[List[ChatCompletionToolParam]] = None,
    custom_llm_provider: Optional[str] = None,
) -> bool:
    """
    Returns true if the prompt is valid for prompt caching.

    OpenAI + Anthropic providers have a minimum token count of 1024 for prompt caching.
    """
    try:
        if messages is None and tools is None:
            return False
        if custom_llm_provider is not None and not model.startswith(
            custom_llm_provider
        ):
            model = custom_llm_provider + "/" + model
        token_count = token_counter(
            messages=messages,
            tools=tools,
            model=model,
            use_default_image_token_count=True,
        )
        return token_count >= MINIMUM_PROMPT_CACHE_TOKEN_COUNT
    except Exception as e:
        log.error(f"Error in is_prompt_caching_valid_prompt: {e}")
        return False


def extract_duration_from_srt_or_vtt(srt_or_vtt_content: str) -> Optional[float]:
    """
    Extracts the total duration (in seconds) from SRT or VTT content.

    Args:
        srt_or_vtt_content (str): The content of an SRT or VTT file as a string.

    Returns:
        Optional[float]: The total duration in seconds, or None if no timestamps are found.
    """
    # Regular expression to match timestamps in the format "hh:mm:ss,ms" or "hh:mm:ss.ms"
    timestamp_pattern = r"(\d{2}):(\d{2}):(\d{2})[.,](\d{3})"

    timestamps = re.findall(timestamp_pattern, srt_or_vtt_content)

    if not timestamps:
        return None

    # Convert timestamps to seconds and find the max (end time)
    durations = []
    for match in timestamps:
        hours, minutes, seconds, milliseconds = map(int, match)
        total_seconds = hours * 3600 + minutes * 60 + seconds + milliseconds / 1000.0
        durations.append(total_seconds)

    return max(durations) if durations else None


def _add_path_to_api_base(api_base: str, ending_path: str) -> str:
    """
    Adds an ending path to an API base URL while preventing duplicate path segments.

    Args:
        api_base: Base URL string
        ending_path: Path to append to the base URL

    Returns:
        Modified URL string with proper path handling
    """
    original_url = httpx.URL(api_base)
    base_url = original_url.copy_with(params={})  # Removes query params
    base_path = original_url.path.rstrip("/")
    end_path = ending_path.lstrip("/")

    # Split paths into segments
    base_segments = [s for s in base_path.split("/") if s]
    end_segments = [s for s in end_path.split("/") if s]

    # Find overlapping segments from the end of base_path and start of ending_path
    final_segments = []
    for i in range(len(base_segments)):
        if base_segments[i:] == end_segments[: len(base_segments) - i]:
            final_segments = base_segments[:i] + end_segments
            break
    else:
        # No overlap found, just combine all segments
        final_segments = base_segments + end_segments

    # Construct the new path
    modified_path = "/" + "/".join(final_segments)
    modified_url = base_url.copy_with(path=modified_path)

    # Re-add the original query parameters
    return str(modified_url.copy_with(params=original_url.params))


def get_standard_openai_params(params: dict) -> dict:
    return {
        k: v
        for k, v in params.items()
        if k in config.OPENAI_CHAT_COMPLETION_PARAMS and v is not None
    }


def get_non_default_completion_params(kwargs: dict) -> dict:
    openai_params = config.OPENAI_CHAT_COMPLETION_PARAMS
    default_params = openai_params + all_litellm_params
    non_default_params = {
        k: v for k, v in kwargs.items() if k not in default_params
    }  # model-specific params - pass them straight to the model/provider

    return non_default_params


def peek_reasoning_summary_aliases(optional_params: dict) -> Optional[Any]:
    """Read AI-SDK-style reasoning summary from optional_params or nested extra_body.

    Uses key membership (not ``or`` chains) so falsy values like ``""`` are not skipped.
    """
    if "reasoningSummary" in optional_params:
        return optional_params["reasoningSummary"]
    if "reasoning_summary" in optional_params:
        return optional_params["reasoning_summary"]
    extra_body = optional_params.get("extra_body")
    if isinstance(extra_body, dict):
        if "reasoningSummary" in extra_body:
            return extra_body["reasoningSummary"]
        if "reasoning_summary" in extra_body:
            return extra_body["reasoning_summary"]
    return None


def strip_reasoning_summary_aliases_from_optional_params(
    optional_params: dict,
) -> Tuple[dict, Optional[Any]]:
    """Copy optional_params; remove reasoningSummary aliases from top-level and extra_body."""
    op = dict(optional_params)
    rs_val = op.pop("reasoningSummary", None)
    snake_rs_val = op.pop("reasoning_summary", None)
    if rs_val is None:
        rs_val = snake_rs_val
    eb = op.get("extra_body")
    if isinstance(eb, dict):
        eb = dict(eb)
        eb_rs_val = eb.pop("reasoningSummary", None)
        eb_snake_rs_val = eb.pop("reasoning_summary", None)
        if rs_val is None:
            rs_val = eb_rs_val
            if rs_val is None:
                rs_val = eb_snake_rs_val
        if eb:
            op["extra_body"] = eb
        else:
            op.pop("extra_body", None)
    return op, rs_val


def get_non_default_transcription_params(kwargs: dict) -> dict:
    from bound.config.constants import OPENAI_TRANSCRIPTION_PARAMS

    default_params = OPENAI_TRANSCRIPTION_PARAMS + all_litellm_params
    non_default_params = {k: v for k, v in kwargs.items() if k not in default_params}
    return non_default_params

def return_raw_request(endpoint: CallTypes, kwargs: dict) -> RawRequestTypedDict:
    from datetime import datetime
    from bound.plane.delegator import Logging

    litellm_logging_obj = Logging(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": "hi"}],
        stream=False,
        call_type="acompletion",
        litellm_call_id="1234",
        start_time=datetime.now(),
        function_id="1234",
        log_raw_request_response=True,
    )

    llm_api_endpoint = getattr(litellm, endpoint.value)

    received_exception = ""

    try:
        llm_api_endpoint(
            **kwargs,
            litellm_logging_obj=litellm_logging_obj,
            api_key="my-fake-api-key",  # 👈 ensure the request fails
        )
    except Exception as e:
        received_exception = str(e)

    raw_request_typed_dict = litellm_logging_obj.model_call_details.get(
        "raw_request_typed_dict"
    )
    if raw_request_typed_dict:
        return cast(RawRequestTypedDict, raw_request_typed_dict)
    else:
        return RawRequestTypedDict(
            error=received_exception,
        )

def get_empty_usage() -> Usage:
    return Usage(
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=0,
    )

def should_run_mock_completion(
    mock_response: Optional[Any],
    mock_tool_calls: Optional[Any],
    mock_timeout: Optional[Any],
) -> bool:
    if mock_response or mock_tool_calls or mock_timeout:
        return True
    return False


def __getattr__(name: str) -> Any:
    """Lazy import handler for utils module with cached registry for improved performance."""
    # Use cached registry from _lazy_imports instead of importing tuples every time
    from litellm._lazy_imports import _get_lazy_import_registry
    registry = _get_lazy_import_registry()

    # Check if name is in registry and call the cached handler function
    if name in registry:
        handler_func = registry[name]
        return handler_func(name)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")