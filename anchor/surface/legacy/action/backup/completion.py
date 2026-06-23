# anchor.surface.legacy.action.backup.completion
## @lineage: anchor.surface.legacy.action.completion
import asyncio
import contextvars
import datetime
import inspect
import json
import os
import random
import sys
import time
import traceback
from copy import deepcopy
from functools import partial
from typing import Any, Dict, List, Literal, Optional, Tuple, Type, Union, cast
from aiohttp import ClientSession
import httpx
import openai
from pydantic import BaseModel

from litellm.llms.anthropic.chat import AnthropicChatCompletion

from anchor.switch.params import Choices, Message, ModelResponse, Usage, ModelResponseStream
from anchor.surface.legacy.types.mapping.exception import exception_type
from anchor.surface.legacy.types.utils import all_litellm_params
from anchor.base.config.resolver import config
from anchor.base.exception import LiteLLMUnknownProvider
from anchor.model.info.support import supports_httpx_timeout
from anchor.model.provider.manager import ProviderConfigManager
from anchor.model.provider.resolver import get_llm_provider
from anchor.model.provider.types import ProviderTypes
from anchor.model.llm.types.openai import AllMessageValues
from anchor.model.llm.types.anthropic import AnthropicThinkingParam
from anchor.model.llm.types.openai import (
    ChatCompletionAudioParam,
    ChatCompletionModality,
    ChatCompletionPredictionContentParam,
    OpenAIWebSearchOptions,
)

from bound.channel.wrapper import client
from bound.channel.action.handler.param.optional import get_optional_params
from bound.channel.action.handler.completor import CompletionHandler
from bound.channel.action.handler.param.litellm import get_litellm_params
from bound.channel.action.timeout import CompletionTimeout
from bound.channel.action.handler.param.validator import (
    validate_and_fix_openai_messages,
    validate_and_fix_openai_tools,
    validate_and_fix_thinking_param,
    validate_chat_completion_tool_choice,
    validate_openai_optional_params
)
from bound.inter.llms.openai.completion import OpenAIChatCompletion
from bound.transport.stream.wrapper import CustomStreamWrapper
from bound.xor.secret.manager import get_secret_bool, get_secret_str

from xphi.scope.plane.delegator import Logging as LiteLLMLoggingObj
from xphi.scope.plane.trace.dd import tracer

from watcher.plane.emitter import get_emitter

log = get_emitter("bound.completion")

openai_chat_completions = OpenAIChatCompletion()
anthropic_chat_completions = AnthropicChatCompletion()
completion_handler = CompletionHandler()

def get_non_default_completion_params(kwargs: dict) -> dict:
    openai_params = config.OPENAI_CHAT_COMPLETION_PARAMS
    default_params = openai_params + all_litellm_params
    non_default_params = {
        k: v for k, v in kwargs.items() if k not in default_params
    }  # model-specific params - pass them straight to the model/provider

    return non_default_params

class Completions:
    def __init__(self, params, router_obj: Optional[Any]):
        self.params = params
        self.router_obj = router_obj

    def create(self, messages, model=None, **kwargs):
        for k, v in kwargs.items():
            self.params[k] = v
        model = model or self.params.get("model")
        if self.router_obj is not None:
            return self.router_obj.completion(model=model, messages=messages, **self.params)
        return completion(model=model, messages=messages, **self.params)


def _should_allow_input_examples(custom_llm_provider: Optional[str], model: str) -> bool:
    return True

def _drop_input_examples_from_tool(tool: dict) -> dict:
    tool_copy = tool.copy()
    tool_copy.pop("input_examples", None)
    function = tool_copy.get("function")
    if isinstance(function, dict):
        function = function.copy()
        function.pop("input_examples", None)
        tool_copy["function"] = function
    return tool_copy

def _drop_input_examples_from_tools(tools: Optional[List[dict]]) -> Optional[List[dict]]:
    if tools is None:
        return None
    return [_drop_input_examples_from_tool(tool) if isinstance(tool, dict) else tool for tool in tools]


@tracer.wrap()
@client
def completion(
    model: str,
    messages: List = [],
    timeout: Optional[Union[float, str, httpx.Timeout]] = None,
    temperature: Optional[float] = None,
    top_p: Optional[float] = None,
    n: Optional[int] = None,
    stream: Optional[bool] = None,
    stream_options: Optional[dict] = None,
    stop=None,
    max_completion_tokens: Optional[int] = None,
    max_tokens: Optional[int] = None,
    modalities: Optional[List[ChatCompletionModality]] = None,
    prediction: Optional[ChatCompletionPredictionContentParam] = None,
    audio: Optional[ChatCompletionAudioParam] = None,
    presence_penalty: Optional[float] = None,
    frequency_penalty: Optional[float] = None,
    logit_bias: Optional[dict] = None,
    user: Optional[str] = None,
    reasoning_effort: Optional[Literal["none", "minimal", "low", "medium", "high", "xhigh", "default"]] = None,
    verbosity: Optional[Literal["low", "medium", "high"]] = None,
    response_format: Optional[Union[dict, Type[BaseModel]]] = None,
    seed: Optional[int] = None,
    tools: Optional[List] = None,
    tool_choice: Optional[Union[str, dict]] = None,
    logprobs: Optional[bool] = None,
    top_logprobs: Optional[int] = None,
    parallel_tool_calls: Optional[bool] = None,
    web_search_options: Optional[OpenAIWebSearchOptions] = None,
    include_server_side_tool_invocations: Optional[bool] = None,
    deployment_id=None,
    extra_headers: Optional[dict] = None,
    safety_identifier: Optional[str] = None,
    service_tier: Optional[str] = None,
    functions: Optional[List] = None,
    function_call: Optional[str] = None,
    base_url: Optional[str] = None,
    api_version: Optional[str] = None,
    api_key: Optional[str] = None,
    model_list: Optional[list] = None,
    thinking: Optional[AnthropicThinkingParam] = None,
    shared_session: Optional["ClientSession"] = None,
    enable_json_schema_validation: Optional[bool] = None,
    **kwargs,
) -> Union[ModelResponse, CustomStreamWrapper]:
    log.debug(f"[bound.completion] 진입: model={model}, custom_llm_provider={kwargs.get('custom_llm_provider')}, stream={stream}")

    if model is None:
        raise ValueError("model param not passed in.")

    ## 메시지 및 옵셔널 파라미터 1차 검증
    messages = validate_and_fix_openai_messages(messages=messages)
    tools = validate_and_fix_openai_tools(tools=tools)
    tool_choice = validate_chat_completion_tool_choice(tool_choice=tool_choice)
    stop = validate_openai_optional_params(stop=stop)
    thinking = validate_and_fix_thinking_param(thinking=thinking)

    args = locals()
    api_base = kwargs.get("api_base", None) or base_url
    logger_fn = kwargs.get("logger_fn", None)
    verbose = kwargs.get("verbose", False)
    custom_llm_provider = kwargs.get("custom_llm_provider", None)
    litellm_logging_obj = kwargs.get("litellm_logging_obj", None)
    acompletion = kwargs.get("acompletion", False)
    client_instance = kwargs.get("client", None)
    
    ## 헤더 초기화 및 병합
    headers = kwargs.get("headers", {}) or {}
    if extra_headers:
        headers.update(extra_headers)

    ## Provider 추론 및 Model Name 정규화
    if kwargs.get("azure", False) is True:
        custom_llm_provider = "azure"
    if deployment_id is not None:
        model = deployment_id
        custom_llm_provider = "azure"

    model, custom_llm_provider, dynamic_api_key, api_base = get_llm_provider(
        model=model,
        custom_llm_provider=custom_llm_provider,
        api_base=api_base,
        api_key=api_key,
    )
    
    log.debug(f"[bound.completion] Provider 정규화 완료: resolved_model={model}, provider={custom_llm_provider}, api_base={api_base}")

    if not _should_allow_input_examples(custom_llm_provider=custom_llm_provider, model=model):
        tools = _drop_input_examples_from_tools(tools=tools)

    ## 데이터 클래스 껍데기 세팅 (의존성 유지를 위한 최소 단위)
    model_response = ModelResponse()
    setattr(model_response, "usage", config.Usage())
    if hasattr(model_response, "_hidden_params"):
        model_response._hidden_params["custom_llm_provider"] = custom_llm_provider
        model_response._hidden_params["region_name"] = kwargs.get("aws_region_name", None)

    ## 타임아웃 결정
    timeout = CompletionTimeout.resolve(
        timeout, kwargs, custom_llm_provider, global_timeout=config.request_timeout,
        supports_httpx_timeout=supports_httpx_timeout,
    )

    ## 프롬프트 및 시스템 메시지 매핑 로직 (Surgent 환경 호환성)
    base_model = kwargs.get("base_model") or (kwargs.get("model_info", {}).get("base_model"))
    provider_config: Optional[Any] = None
    if custom_llm_provider in [p.value for p in ProviderTypes]:
        provider_config = ProviderConfigManager.get_provider_chat_config(
            model=model, provider=ProviderTypes(custom_llm_provider), base_model=base_model,
        )

    if provider_config is not None:
        messages = provider_config.translate_developer_role_to_system_role(messages=messages)

    if kwargs.get("supports_system_message") is False:
        messages = map_system_message_pt(messages=messages)

    if kwargs.get("litellm_system_prompt"):
        messages = add_system_prompt_to_messages(
            messages=messages, system_prompt=kwargs.get("litellm_system_prompt"), merge_with_first_system=True
        )

    ## 파라미터 필터링 (불필요한 인자를 각 Provider에 맞게 쳐냄)
    api_key = dynamic_api_key or api_key
    optional_param_args = {
        "model": model,
        "custom_llm_provider": custom_llm_provider,
        "base_model": base_model,
        "max_retries": kwargs.get("max_retries", kwargs.get("num_retries")),
    }
    
    ## 나머지 옵셔널 파라미터 병합
    optional_param_args.update({k: v for k, v in args.items() if k in [
        "functions", "function_call", "temperature", "top_p", "n", "stream", "stream_options", 
        "stop", "max_tokens", "max_completion_tokens", "modalities", "prediction", "audio", 
        "presence_penalty", "frequency_penalty", "logit_bias", "user", "response_format", 
        "seed", "tools", "tool_choice", "logprobs", "top_logprobs", "parallel_tool_calls", 
        "reasoning_effort", "thinking", "web_search_options", "safety_identifier", "service_tier"
    ]})
    
    non_default_params = get_non_default_completion_params(kwargs=kwargs)
    optional_params = get_optional_params(**optional_param_args, **non_default_params)
    safe_kwargs = kwargs.copy()
    for key in ["acompletion", "api_key", "custom_llm_provider", "api_base"]:
        safe_kwargs.pop(key, None)

    litellm_params = get_litellm_params(
        acompletion=acompletion, 
        api_key=api_key, 
        custom_llm_provider=custom_llm_provider, 
        api_base=api_base, 
        **safe_kwargs
    )

    ## 로깅 환경 변수 강제 업데이트
    logging: LiteLLMLoggingObj = cast(LiteLLMLoggingObj, litellm_logging_obj)
    if logging:
        logging.update_environment_variables(
            model=model, user=user, optional_params=optional_params, 
            litellm_params=litellm_params, custom_llm_provider=custom_llm_provider,
        )

    try:
        ## [A] OpenAI 및 호환 (Local, vLLM, Groq, Custom 등)
        if custom_llm_provider in ["openai", "custom_openai", "azure"] or custom_llm_provider in config.openai_compatible_providers:
            log.debug(f"[bound.completion] OpenAI 호환 Provider 분기 진입 (provider: {custom_llm_provider})")
            if custom_llm_provider == "azure" and deployment_id is None:
                 deployment_id = model
                 
            # OpenAI 전역 객체 오염 방지를 위해 인자로 명시적 전달
            actual_api_key = api_key or config.api_key or get_secret("OPENAI_API_KEY")
            actual_api_base = api_base or config.api_base or get_secret("OPENAI_BASE_URL") or "https://api.openai.com/v1"
            use_base_llm = get_secret_bool("EXPERIMENTAL_OPENAI_BASE_LLM_HTTP_HANDLER")
            log.debug(f"[bound.completion] use_base_llm 플래그 확인 결과: {use_base_llm}")
            
            if use_base_llm:
                log.debug("[bound.completion] 👉 completion_handler.completion() 호출 (OpenAI Base LLM HTTP Handler)")
                response = completion_handler.completion(
                    model=model, messages=messages, api_base=actual_api_base, api_key=actual_api_key,
                    custom_llm_provider=custom_llm_provider, model_response=model_response, 
                    optional_params=optional_params, litellm_params=litellm_params, logging_obj=logging,
                    timeout=timeout, shared_session=shared_session, acompletion=acompletion, 
                    stream=stream, headers=headers, client=client_instance, provider_config=provider_config,
                    encoding=None  # encoding 인자가 필수라면 여기에 추가
                )
            else:
                log.debug("[bound.completion] 👉 openai_chat_completions.completion() 호출 (기존 핸들러)")
                ctx = openai_chat_completions.create_context(
                    model=model, messages=messages, api_base=actual_api_base, api_key=actual_api_key,
                    custom_llm_provider=custom_llm_provider, model_response=model_response,
                    optional_params=optional_params, litellm_params=litellm_params, logging_obj=logging,
                    timeout=timeout, shared_session=shared_session, acompletion=acompletion,
                    headers=headers, client=client_instance, organization=kwargs.get("organization")
                )
                response = openai_chat_completions.completion(ctx, model_response)
        elif custom_llm_provider == "anthropic":
            log.debug("[bound.completion] 👉 anthropic_chat_completions.completion() 호출 (Anthropic 분기)")
            actual_api_key = api_key or config.anthropic_key or get_secret("ANTHROPIC_API_KEY")
            actual_api_base = api_base or get_secret("ANTHROPIC_API_BASE") or "https://api.anthropic.com/v1/messages"
            if not actual_api_base.endswith("/v1/messages") and not get_secret_bool("LITELLM_ANTHROPIC_DISABLE_URL_SUFFIX"):
                actual_api_base += "/v1/messages"

            response = anthropic_chat_completions.completion(
                model=model, messages=messages, api_base=actual_api_base, api_key=actual_api_key,
                custom_llm_provider=custom_llm_provider, model_response=model_response,
                optional_params=optional_params, litellm_params=litellm_params, logging_obj=logging,
                timeout=timeout, headers=headers, client=client_instance, acompletion=acompletion,
                # encoding=_get_encoding(),
                custom_prompt_dict=config.custom_prompt_dict
            )
        elif custom_llm_provider == "ollama":
            log.debug("[bound.completion] 👉 completion_handler.completion() 호출 (Ollama 분기)")
            actual_api_base = api_base or get_secret("OLLAMA_API_BASE") or "http://localhost:11434"
            if api_key and "Authorization" not in headers:
                headers["Authorization"] = f"Bearer {api_key}"

            response = completion_handler.completion(
                model=model, messages=messages, api_base=actual_api_base, api_key=api_key,
                custom_llm_provider="ollama", model_response=model_response,
                optional_params=optional_params, litellm_params=litellm_params, logging_obj=logging,
                timeout=timeout, shared_session=shared_session, acompletion=acompletion,
                stream=stream, headers=headers, client=client_instance,
                encoding=None # encoding 인자 필요 시 수정
            )
        elif custom_llm_provider == "huggingface":
            log.debug("[bound.completion] 👉 completion_handler.completion() 호출 (Huggingface 분기)")
            actual_api_key = api_key or config.huggingface_key or get_secret("HF_TOKEN")
            response = completion_handler.completion(
                model=model, messages=messages, api_base=api_base, api_key=actual_api_key,
                custom_llm_provider=custom_llm_provider, model_response=model_response,
                optional_params=optional_params, litellm_params=litellm_params, logging_obj=logging,
                timeout=timeout, acompletion=acompletion, stream=stream, headers=headers, 
                client=client_instance,
                encoding=None # encoding 인자 필요 시 수정
            )
        else:
            log.error(f"[bound.completion] 알 수 없는 Provider 예외 발생: {custom_llm_provider}")
            raise LiteLLMUnknownProvider(model=model, custom_llm_provider=custom_llm_provider)

        if stream is True and isinstance(response, ModelResponseStream):
            log.debug("[bound.completion] 스트림 요청 성공: CustomStreamWrapper를 반환합니다.")
            return CustomStreamWrapper(
                completion_stream=response, model=model, custom_llm_provider=custom_llm_provider, logging_obj=logging,
            )
            
        log.debug("[bound.completion] 응답이 성공적으로 반환되었습니다.")
        return response
    except Exception as e:
        log.error(f"[bound.completion] 예외 발생: {str(e)}")
        if logging:
            logging.post_call(
                input=messages, api_key=api_key, original_response=str(e), additional_args={"headers": headers},
            )
        raise exception_type(
            model=model, custom_llm_provider=custom_llm_provider, original_exception=e,
            completion_kwargs=args, extra_kwargs=kwargs,
        )

def add_system_prompt_to_messages(
    messages: List[AllMessageValues],
    system_prompt: str,
    merge_with_first_system: bool = False,
) -> List[AllMessageValues]:
    if not system_prompt:
        return list(messages)

    if merge_with_first_system and messages and messages[0].get("role") == "system":
        first = dict(messages[0])
        existing_content = first.get("content", "")
        merged_content: Union[str, List[Dict[str, str]]]
        if isinstance(existing_content, str):
            merged_content = f"{system_prompt.strip()}\n\n{existing_content}"
        elif isinstance(existing_content, list):
            merged_content = [{"type": "text", "text": system_prompt.strip()}] + list(
                existing_content
            )
        else:
            merged_content = [{"type": "text", "text": system_prompt.strip()}]
        first["content"] = merged_content
        return [cast(AllMessageValues, first)] + list(messages[1:])

    system_message: AllMessageValues = {"role": "system", "content": system_prompt}
    return [system_message, *messages]

def map_system_message_pt(messages: list) -> list:
    new_messages = []
    for i, m in enumerate(messages):
        if m["role"] == "system":
            if i < len(messages) - 1:
                next_m = messages[i + 1]
                next_role = next_m["role"]
                if (next_role == "user" or next_role == "assistant"):
                    next_m["content"] = m["content"] + " " + next_m["content"]
                elif next_role == "system":
                    new_message = {"role": "user", "content": m["content"]}
                    new_messages.append(new_message)
            else:
                new_message = {"role": "user", "content": m["content"]}
                new_messages.append(new_message)
        else:
            new_messages.append(m)
    return new_messages