# anchor.surface.legacy.action.acompletion
## @lineage: bound.bridge.action.acompletion
## @lineage: bound.client.action.acompletion
## @lineage: anchor.router.action.acompletion
## @lineage: bound.router.action.acompletion
## @lineage: bound.channel.router.action.acompletion
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
from aiohttp import ClientSession
import httpx
import openai
import tiktoken
from pydantic import BaseModel
from typing_extensions import overload
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncIterator,
    Callable,
    Coroutine,
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

from anchor.base.exception import Timeout
from anchor.switch.params import ModelResponse

from bound.transport.stream.wrapper import CustomStreamWrapper
from bound.channel.wrapper import client
from xphi.scope.plane.trace.dd import tracer
from xphi.scope.plane.delegator import Logging as LiteLLMLoggingObj

from bound.channel.support.helpers import safe_deep_copy, filter_internal_params
from bound.channel.action.handler.asyncify import run_async_function
from anchor.surface.legacy.mapping.exception import exception_type
from anchor.surface.legacy.types.utils import (
    CustomPricingLiteLLMParams,
    ModelResponseStream,
    RawRequestTypedDict,
    StreamingChoices,
)
from anchor.model.llm.types.anthropic import AnthropicThinkingParam
from anchor.model.llm.types.openai import ChatCompletionAudioParam, ChatCompletionModality, ChatCompletionPredictionContentParam, OpenAIWebSearchOptions
from anchor.base.exception import Timeout
from anchor.model.provider.resolver import get_llm_provider

from arch.proto.phase.gate import uuid
from watcher.plane.emitter import get_emitter

log = get_emitter("action.acompletion")

class AsyncCompletions:
    def __init__(self, params, router_obj: Optional[Any]):
        self.params = params
        self.router_obj = router_obj

    async def create(self, messages, model=None, **kwargs):
        for k, v in kwargs.items():
            self.params[k] = v
        model = model or self.params.get("model")
        if self.router_obj is not None:
            response = await self.router_obj.acompletion(
                model=model, messages=messages, **self.params
            )
        else:
            response = await acompletion(model=model, messages=messages, **self.params)
        return response

@tracer.wrap()
@client
async def acompletion(  # noqa: PLR0915
    model: str,
    messages: List = [],
    functions: Optional[List] = None,
    function_call: Optional[str] = None,
    timeout: Optional[Union[float, int]] = None,
    temperature: Optional[float] = None,
    top_p: Optional[float] = None,
    n: Optional[int] = None,
    stream: Optional[bool] = None,
    stream_options: Optional[dict] = None,
    stop=None,
    max_tokens: Optional[int] = None,
    max_completion_tokens: Optional[int] = None,
    modalities: Optional[List[ChatCompletionModality]] = None,
    prediction: Optional[ChatCompletionPredictionContentParam] = None,
    audio: Optional[ChatCompletionAudioParam] = None,
    presence_penalty: Optional[float] = None,
    frequency_penalty: Optional[float] = None,
    logit_bias: Optional[dict] = None,
    user: Optional[str] = None,
    response_format: Optional[Union[dict, Type[BaseModel]]] = None,
    seed: Optional[int] = None,
    tools: Optional[List] = None,
    tool_choice: Optional[Union[str, dict]] = None,
    parallel_tool_calls: Optional[bool] = None,
    logprobs: Optional[bool] = None,
    top_logprobs: Optional[int] = None,
    deployment_id=None,
    reasoning_effort: Optional[
        Literal["none", "minimal", "low", "medium", "high", "xhigh", "default"]
    ] = None,
    verbosity: Optional[Literal["low", "medium", "high"]] = None,
    safety_identifier: Optional[str] = None,
    service_tier: Optional[str] = None,
    base_url: Optional[str] = None,
    api_version: Optional[str] = None,
    api_key: Optional[str] = None,
    model_list: Optional[list] = None,  # pass in a list of api_base,keys, etc.
    extra_headers: Optional[dict] = None,
    thinking: Optional[AnthropicThinkingParam] = None,
    web_search_options: Optional[OpenAIWebSearchOptions] = None,
    include_server_side_tool_invocations: Optional[bool] = None,
    shared_session: Optional["ClientSession"] = None,
    enable_json_schema_validation: Optional[bool] = None,
    **kwargs,
) -> Union[ModelResponse, CustomStreamWrapper]:
    fallbacks = kwargs.get("fallbacks", None)
    mock_timeout = kwargs.get("mock_timeout", None)
    if mock_timeout is True:
        await _handle_mock_timeout_async(mock_timeout, timeout, model)

    loop = asyncio.get_event_loop()
    custom_llm_provider = kwargs.get("custom_llm_provider", None)
    litellm_logging_obj = kwargs.get("litellm_logging_obj", None)
    if isinstance(litellm_logging_obj, LiteLLMLoggingObj) and (
        litellm_logging_obj.should_run_prompt_management_hooks(
            prompt_id=kwargs.get("prompt_id", None),
            non_default_params=kwargs,
            tools=tools,
        )
    ):
        (
            model,
            messages,
            _,
        ) = await litellm_logging_obj.async_get_chat_completion_prompt(
            model=model,
            messages=messages,
            non_default_params=kwargs,
            prompt_id=kwargs.get("prompt_id", None),
            prompt_variables=kwargs.get("prompt_variables", None),
            tools=tools,
            prompt_label=kwargs.get("prompt_label", None),
            prompt_version=kwargs.get("prompt_version", None),
        )
        if tools is not None and len(tools) == 0:
            tools = None

    if shared_session is not None:
        log.debug(f"🔄 SHARED SESSION: acompletion called with shared_session (ID: {id(shared_session)})")
    else:
        log.debug("🔄 NO SHARED SESSION: acompletion called without shared_session")

    completion_kwargs = {
        "model": model,
        "messages": messages,
        "functions": functions,
        "function_call": function_call,
        "timeout": timeout,
        "temperature": temperature,
        "top_p": top_p,
        "n": n,
        "stream": stream,
        "stream_options": stream_options,
        "stop": stop,
        "max_tokens": max_tokens,
        "max_completion_tokens": max_completion_tokens,
        "modalities": modalities,
        "prediction": prediction,
        "audio": audio,
        "presence_penalty": presence_penalty,
        "frequency_penalty": frequency_penalty,
        "logit_bias": logit_bias,
        "user": user,
        "response_format": response_format,
        "seed": seed,
        "tools": tools,
        "tool_choice": tool_choice,
        "parallel_tool_calls": parallel_tool_calls,
        "logprobs": logprobs,
        "top_logprobs": top_logprobs,
        "deployment_id": deployment_id,
        "base_url": base_url,
        "api_version": api_version,
        "api_key": api_key,
        "model_list": model_list,
        "reasoning_effort": reasoning_effort,
        "safety_identifier": safety_identifier,
        "service_tier": service_tier,
        "extra_headers": extra_headers,
        "acompletion": True,  # assuming this is a required parameter
        "thinking": thinking,
        "web_search_options": web_search_options,
        "include_server_side_tool_invocations": include_server_side_tool_invocations,
        "shared_session": shared_session,
        "enable_json_schema_validation": enable_json_schema_validation,
    }
    if custom_llm_provider is None:
        _, custom_llm_provider, _, _ = get_llm_provider(
            model=model,
            custom_llm_provider=custom_llm_provider,
            api_base=completion_kwargs.get("base_url", None),
        )

    if fallbacks is not None:
        response = await async_completion_with_fallbacks(
            **completion_kwargs, kwargs={"fallbacks": fallbacks, **kwargs}
        )
        if response is None:
            raise Exception("No response from fallbacks. Got none.")
        return response

    ### APPLY MOCK DELAY ###
    mock_delay = kwargs.get("mock_delay")
    mock_response = kwargs.get("mock_response")
    mock_tool_calls = kwargs.get("mock_tool_calls")
    mock_timeout = kwargs.get("mock_timeout")
    if mock_delay and (mock_response or mock_tool_calls or mock_timeout): 
        await asyncio.sleep(mock_delay)

    try:
        # Use a partial function to pass your keyword arguments
        func = partial(completion, **completion_kwargs, **kwargs)

        # Add the context to the function
        ctx = contextvars.copy_context()
        func_with_context = partial(ctx.run, func)

        init_response = await loop.run_in_executor(None, func_with_context)
        if isinstance(init_response, dict) or isinstance(
            init_response, ModelResponse
        ):  ## CACHING SCENARIO
            if isinstance(init_response, dict):
                response = ModelResponse(**init_response)
            response = init_response
        elif asyncio.iscoroutine(init_response):
            response = await init_response
        else:
            response = init_response  # type: ignore

        if isinstance(response, CustomStreamWrapper):
            response.set_logging_event_loop(loop=loop)
        return response
    except Exception as e:
        custom_llm_provider = custom_llm_provider or "openai"
        raise exception_type(
            model=model,
            custom_llm_provider=custom_llm_provider,
            original_exception=e,
            completion_kwargs=completion_kwargs,
            extra_kwargs=kwargs,
        )

async def _handle_mock_timeout_async(
    mock_timeout: Optional[bool],
    timeout: Optional[Union[float, str, httpx.Timeout]],
    model: str,
):
    if mock_timeout is True and timeout is not None:
        await _sleep_for_timeout_async(timeout)
        raise Timeout(
            message="This is a mock timeout error",
            llm_provider="openai",
            model=model,
        )

async def _sleep_for_timeout_async(timeout: Union[float, str, httpx.Timeout]):
    if isinstance(timeout, float):
        await asyncio.sleep(timeout)
    elif isinstance(timeout, str):
        await asyncio.sleep(float(timeout))
    elif isinstance(timeout, httpx.Timeout) and timeout.connect is not None:
        await asyncio.sleep(timeout.connect)

async def async_completion_with_fallbacks(**kwargs):
    nested_kwargs = kwargs.pop("kwargs", {})
    original_model = kwargs["model"]
    model = original_model
    fallbacks = [original_model] + nested_kwargs.pop("fallbacks", [])
    kwargs.pop("acompletion", None)  # Remove to prevent keyword conflicts
    litellm_call_id = str(uuid.uuid4())
    base_kwargs = {**kwargs, **nested_kwargs, "litellm_call_id": litellm_call_id}

    # fields to remove
    base_kwargs.pop("model", None)  # Remove model as it will be set per fallback
    litellm_logging_obj = base_kwargs.pop("litellm_logging_obj", None)

    # Try each fallback model
    most_recent_exception_str: Optional[str] = None
    for fallback in fallbacks:
        try:
            completion_kwargs = safe_deep_copy(base_kwargs)
            # Handle dictionary fallback configurations
            if isinstance(fallback, dict):
                fallback_config = safe_deep_copy(dict(fallback))
                model = fallback_config.pop("model", original_model)
                completion_kwargs.update(fallback_config)
            else:
                model = fallback

            # Filter out internal parameters that shouldn't be sent to provider APIs
            completion_kwargs = filter_internal_params(completion_kwargs)

            response = await acompletion(
                **completion_kwargs,
                model=model,
                litellm_logging_obj=litellm_logging_obj,
            )

            if response is not None:
                return response

        except Exception as e:
            log.exception(
                f"Fallback attempt failed for model {model}: {str(e)}"
            )
            most_recent_exception_str = str(e)
            continue

    raise Exception(
        f"{most_recent_exception_str}. All fallback attempts failed. Enable verbose logging with `litellm.set_verbose=True` for details."
    )

def completion_with_fallbacks(**kwargs):
    return run_async_function(async_function=async_completion_with_fallbacks, **kwargs)
