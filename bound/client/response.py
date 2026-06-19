# bound.client.response
## @lineage: bound.handler.response
import asyncio
import contextvars
from functools import partial
from typing import (
    TYPE_CHECKING,
    Any,
    Coroutine,
    Dict,
    Iterable,
    List,
    Literal,
    Optional,
    Type,
    Union,
    cast,
)
import httpx
from pydantic import BaseModel

from litellm.completion_extras.litellm_responses_transformation.transformation import LiteLLMResponsesTransformationHandler
from litellm.responses.litellm_completion_transformation.handler import LiteLLMCompletionTransformationHandler

from anchor.config.resolver import config
from anchor.config.constants import request_timeout
from anchor.base.response.transformation import BaseResponsesAPIConfig

from anchor.router.model.provider.resolver import get_llm_provider
from anchor.router.model.types.llms.openai import (
    AllMessageValues,
    PromptObject,
    Reasoning,
    ResponseIncludable,
    ResponseInputParam,
    ResponsesAPIOptionalRequestParams,
    ResponsesAPIResponse,
    ToolChoice,
    ToolParam,
)
from anchor.router.model.types.responses.main import *
from anchor.router.model.types.router import GenericLiteLLMParams
from anchor.router.model.provider.manager import ProviderConfigManager
from anchor.router.model.types.llms.openai import ResponseText

from bound.client.handler.api import ResponseApiHandler
from bound.client.handler.asyncify import run_async_function
from bound.client.wrapper import client
from bound.client.support.template import update_responses_input_with_model_file_ids, update_responses_tools_with_model_file_ids
from bound.client.api.request import ResponsesAPIRequestUtils
from bound.client.support.identity import ResponseIdentityManager
from bound.adapter.llama.llms.openai.data_residency import infer_openai_data_residency

from arch.proto.phase.gate import uuid
from watcher.plane.emitter import get_emitter

log = get_emitter("handler.response")
LiteLLMLoggingObj = Any

api_handler = ResponseApiHandler()
litellm_completion_transformation_handler = LiteLLMCompletionTransformationHandler()

def _has_file_search_tool(tools: Optional[Any]) -> bool:
    """Return True if any tool in the list has type 'file_search'."""
    if not tools:
        return False
    return any(isinstance(t, dict) and t.get("type") == "file_search" for t in tools)

def _apply_prompt_management_to_responses_call(
    input: Union[str, ResponseInputParam],
    model: str,
    custom_llm_provider: Optional[str],
    litellm_logging_obj: Optional[LiteLLMLoggingObj],
    kwargs: Dict[str, Any],
    local_vars: Dict[str, Any],
) -> tuple[Union[str, ResponseInputParam], str, Optional[str]]:
    async_merged = kwargs.pop("_async_prompt_merged_params", None)
    if async_merged is not None:
        for key, value in async_merged.items():
            local_vars[key] = value
        return input, model, custom_llm_provider

    prompt_id = cast(Optional[str], kwargs.get("prompt_id", None))
    prompt_variables = cast(Optional[dict], kwargs.get("prompt_variables", None))
    original_model = model

    if isinstance(input, str):
        client_input: List[AllMessageValues] = [{"role": "user", "content": input}]
    else:
        client_input = [
            item  # type: ignore[misc]
            for item in input
            if isinstance(item, dict) and "role" in item
        ]

    if isinstance(
        litellm_logging_obj, LiteLLMLoggingObj
    ) and litellm_logging_obj.should_run_prompt_management_hooks(
        prompt_id=prompt_id, non_default_params=kwargs
    ):
        (
            model,
            merged_input,
            merged_optional_params,
        ) = litellm_logging_obj.get_chat_completion_prompt(
            model=model,
            messages=client_input,
            non_default_params=kwargs,
            prompt_id=prompt_id,
            prompt_variables=prompt_variables,
            prompt_label=kwargs.get("prompt_label", None),
            prompt_version=kwargs.get("prompt_version", None),
        )
        input = cast(Union[str, ResponseInputParam], merged_input)
        local_vars["input"] = input
        local_vars["model"] = model
        if model != original_model:
            _, custom_llm_provider, _, _ = get_llm_provider(model=model)
            local_vars["custom_llm_provider"] = custom_llm_provider
        for key, value in merged_optional_params.items():
            local_vars[key] = value

    return input, model, custom_llm_provider


# Opt-in via model id (mirrors the `responses/` prefix pattern on chat completions).
_OPENAI_CHAT_COMPLETIONS_RESPONSES_MODEL_PREFIX = "openai/chat_completions/"


def _normalize_openai_chat_completions_responses_model(model: str) -> tuple[str, bool]:
    """
    Strip `openai/chat_completions/<name>` → `openai/<name>` and return True when the
    prefix was applied (same effect as use_chat_completions_api=True).
    """
    if not model.startswith(_OPENAI_CHAT_COMPLETIONS_RESPONSES_MODEL_PREFIX):
        return model, False
    remainder = model[len(_OPENAI_CHAT_COMPLETIONS_RESPONSES_MODEL_PREFIX) :]
    if not remainder:
        return model, False
    return f"openai/{remainder}", True


def _pop_use_chat_completions_api_kw(kwargs: Dict[str, Any]) -> bool:
    """Pop use_chat_completions_api; True when the chat-completions bridge is requested."""
    use_cc = kwargs.pop("use_chat_completions_api", None)
    return bool(use_cc)


def _resolve_model_provider_for_responses(
    model: str,
    custom_llm_provider: Optional[str],
    litellm_params: GenericLiteLLMParams,
    local_vars: Dict[str, Any],
) -> tuple[str, Optional[str]]:
    (
        model,
        custom_llm_provider,
        dynamic_api_key,
        dynamic_api_base,
    ) = get_llm_provider(
        model=model,
        custom_llm_provider=custom_llm_provider,
        api_base=litellm_params.api_base,
        api_key=litellm_params.api_key,
    )
    local_vars["custom_llm_provider"] = custom_llm_provider
    if dynamic_api_key is not None:
        litellm_params.api_key = dynamic_api_key
    if dynamic_api_base is not None:
        litellm_params.api_base = dynamic_api_base
    return model, custom_llm_provider


def _apply_managed_file_id_mapping(
    input: Union[str, ResponseInputParam],
    tools: Optional[Iterable[ToolParam]],
    kwargs: Dict[str, Any],
    local_vars: Dict[str, Any],
) -> tuple[Union[str, ResponseInputParam], Optional[Iterable[ToolParam]]]:
    model_file_id_mapping = kwargs.get("model_file_id_mapping")
    model_info_id = (
        kwargs.get("model_info", {}).get("id")
        if isinstance(kwargs.get("model_info"), dict)
        else None
    )

    input = cast(
        Union[str, ResponseInputParam],
        update_responses_input_with_model_file_ids(
            input=input,
            model_id=model_info_id,
            model_file_id_mapping=model_file_id_mapping,
        ),
    )
    local_vars["input"] = input

    if tools:
        tools = cast(
            Optional[Iterable[ToolParam]],
            update_responses_tools_with_model_file_ids(
                tools=cast(Optional[List[Dict[str, Any]]], tools),
                model_id=model_info_id,
                model_file_id_mapping=model_file_id_mapping,
            ),
        )
        local_vars["tools"] = tools

    return input, tools


def _responses_try_dispatch_mcp_gateway(
    *,
    tools: Optional[Iterable[ToolParam]],
    input: Union[str, ResponseInputParam],
    model: str,
    include: Optional[List[ResponseIncludable]],
    instructions: Optional[str],
    max_output_tokens: Optional[int],
    prompt: Optional[PromptObject],
    metadata: Optional[Dict[str, Any]],
    parallel_tool_calls: Optional[bool],
    previous_response_id: Optional[str],
    reasoning: Optional[Reasoning],
    store: Optional[bool],
    background: Optional[bool],
    stream: Optional[bool],
    temperature: Optional[float],
    text: Any,
    tool_choice: Optional[ToolChoice],
    top_p: Optional[float],
    truncation: Optional[Literal["auto", "disabled"]],
    user: Optional[str],
    extra_headers: Optional[Dict[str, Any]],
    extra_query: Optional[Dict[str, Any]],
    extra_body: Optional[Dict[str, Any]],
    timeout: Optional[Union[float, httpx.Timeout]],
    custom_llm_provider: Optional[str],
    kwargs: Dict[str, Any],
    _is_async: bool,
) -> Optional[Any]:
    """Return a response when MCP gateway handles the call; otherwise None."""
    from bound.client.mcp.proxy import MCPProxyHandler
    if not MCPProxyHandler._should_use_litellm_mcp_gateway(tools=tools):
        return None
    mcp_call_kwargs = {
        "input": input,
        "model": model,
        "include": include,
        "instructions": instructions,
        "max_output_tokens": max_output_tokens,
        "prompt": prompt,
        "metadata": metadata,
        "parallel_tool_calls": parallel_tool_calls,
        "previous_response_id": previous_response_id,
        "reasoning": reasoning,
        "store": store,
        "background": background,
        "stream": stream,
        "temperature": temperature,
        "text": text,
        "tool_choice": tool_choice,
        "tools": tools,
        "top_p": top_p,
        "truncation": truncation,
        "user": user,
        "extra_headers": extra_headers,
        "extra_query": extra_query,
        "extra_body": extra_body,
        "timeout": timeout,
        "custom_llm_provider": custom_llm_provider,
        **kwargs,
    }
    if _is_async:
        return aresponses_api_with_mcp(**mcp_call_kwargs)
    return run_async_function(aresponses_api_with_mcp, **mcp_call_kwargs)


def _responses_try_dispatch_emulated_file_search(
    *,
    tools: Optional[Iterable[ToolParam]],
    input: Union[str, ResponseInputParam],
    model: str,
    responses_api_provider_config: Optional[BaseResponsesAPIConfig],
    use_chat_completions_api: bool,
    include: Optional[List[ResponseIncludable]],
    instructions: Optional[str],
    max_output_tokens: Optional[int],
    prompt: Optional[PromptObject],
    metadata: Optional[Dict[str, Any]],
    parallel_tool_calls: Optional[bool],
    previous_response_id: Optional[str],
    reasoning: Optional[Reasoning],
    store: Optional[bool],
    background: Optional[bool],
    stream: Optional[bool],
    temperature: Optional[float],
    text: Any,
    tool_choice: Optional[ToolChoice],
    top_p: Optional[float],
    truncation: Optional[Literal["auto", "disabled"]],
    user: Optional[str],
    service_tier: Optional[str],
    safety_identifier: Optional[str],
    text_format: Optional[Union[Type[BaseModel], dict]],
    allowed_openai_params: Optional[List[str]],
    extra_headers: Optional[Dict[str, Any]],
    extra_query: Optional[Dict[str, Any]],
    extra_body: Optional[Dict[str, Any]],
    timeout: Optional[Union[float, httpx.Timeout]],
    custom_llm_provider: Optional[str],
    kwargs: Dict[str, Any],
    _is_async: bool,
) -> Optional[Any]:
    from anchor.router.action.search.file import aresponses_with_emulated_file_search
    """Return a response when emulated file_search handles the call; otherwise None."""
    if not _has_file_search_tool(tools) or not (
        responses_api_provider_config is None
        or use_chat_completions_api is True
        or not responses_api_provider_config.supports_native_file_search()
    ):
        return None

    _internal_skip = {"litellm_call_id", "aresponses"}
    emulated_kwargs = {
        "include": include,
        "instructions": instructions,
        "max_output_tokens": max_output_tokens,
        "prompt": prompt,
        "metadata": metadata,
        "parallel_tool_calls": parallel_tool_calls,
        "previous_response_id": previous_response_id,
        "reasoning": reasoning,
        "store": store,
        "background": background,
        "stream": stream,
        "temperature": temperature,
        "text": text,
        "tool_choice": tool_choice,
        "top_p": top_p,
        "truncation": truncation,
        "user": user,
        "service_tier": service_tier,
        "safety_identifier": safety_identifier,
        "text_format": text_format,
        "allowed_openai_params": allowed_openai_params,
        "extra_headers": extra_headers,
        "extra_query": extra_query,
        "extra_body": extra_body,
        "timeout": timeout,
        "custom_llm_provider": custom_llm_provider,
        **(
            {
                **(
                    {"use_chat_completions_api": True}
                    if use_chat_completions_api
                    else {}
                ),
                **{k: v for k, v in kwargs.items() if k not in _internal_skip},
            }
        ),
    }
    if _is_async:
        return aresponses_with_emulated_file_search(
            input=input, model=model, tools=tools, **emulated_kwargs
        )
    return run_async_function(
        aresponses_with_emulated_file_search,
        input=input,
        model=model,
        tools=tools,
        **emulated_kwargs,
    )


@client
def responses(
    input: Union[str, ResponseInputParam],
    model: str,
    include: Optional[List[ResponseIncludable]] = None,
    instructions: Optional[str] = None,
    max_output_tokens: Optional[int] = None,
    prompt: Optional[PromptObject] = None,
    metadata: Optional[Dict[str, Any]] = None,
    parallel_tool_calls: Optional[bool] = None,
    previous_response_id: Optional[str] = None,
    reasoning: Optional[Reasoning] = None,
    store: Optional[bool] = None,
    background: Optional[bool] = None,
    stream: Optional[bool] = None,
    temperature: Optional[float] = None,
    text: Optional["ResponseText"] = None,
    text_format: Optional[Union[Type["BaseModel"], dict]] = None,
    tool_choice: Optional[ToolChoice] = None,
    tools: Optional[Iterable[ToolParam]] = None,
    top_p: Optional[float] = None,
    truncation: Optional[Literal["auto", "disabled"]] = None,
    user: Optional[str] = None,
    service_tier: Optional[str] = None,
    safety_identifier: Optional[str] = None,
    # Use the following arguments if you need to pass additional parameters to the API that aren't available via kwargs.
    # The extra values given here take precedence over values defined on the client or passed to this method.
    extra_headers: Optional[Dict[str, Any]] = None,
    extra_query: Optional[Dict[str, Any]] = None,
    extra_body: Optional[Dict[str, Any]] = None,
    timeout: Optional[Union[float, httpx.Timeout]] = None,
    # LiteLLM specific params,
    allowed_openai_params: Optional[List[str]] = None,
    custom_llm_provider: Optional[str] = None,
    **kwargs,
):
    """
    Synchronous version of the Responses API.
    Uses the synchronous HTTP handler to make requests.
    """
    local_vars = locals()

    try:
        litellm_logging_obj: LiteLLMLoggingObj = kwargs.get("litellm_logging_obj")  # type: ignore
        litellm_call_id: Optional[str] = kwargs.get("litellm_call_id", None)
        _is_async = kwargs.pop("aresponses", False) is True
        use_chat_completions_api = _pop_use_chat_completions_api_kw(kwargs)

        # Convert text_format to text parameter if provided
        text = ResponsesAPIRequestUtils.convert_text_format_to_text_param(
            text_format=text_format, text=text
        )
        if text is not None:
            # Update local_vars to include the converted text parameter
            local_vars["text"] = text

        # get llm provider logic
        litellm_params = GenericLiteLLMParams(**kwargs)
        _stripped_model, _from_chat_completions_prefix = (
            _normalize_openai_chat_completions_responses_model(model)
        )
        model = _stripped_model
        local_vars["model"] = model
        use_chat_completions_api = (
            use_chat_completions_api or _from_chat_completions_prefix
        )

        model, custom_llm_provider = _resolve_model_provider_for_responses(
            model=model,
            custom_llm_provider=custom_llm_provider,
            litellm_params=litellm_params,
            local_vars=local_vars,
        )

        #########################################################
        # PROMPT MANAGEMENT
        # If aresponses() already ran the async hook, it pops prompt_id and
        # passes the result via _async_prompt_merged_params — apply those
        # directly and skip the sync hook to avoid double-merging.
        #########################################################
        input, model, custom_llm_provider = _apply_prompt_management_to_responses_call(
            input=input,
            model=model,
            custom_llm_provider=custom_llm_provider,
            litellm_logging_obj=litellm_logging_obj,
            kwargs=kwargs,
            local_vars=local_vars,
        )

        #########################################################
        # Update input and tools with provider-specific file IDs if managed files are used
        #########################################################
        input, tools = _apply_managed_file_id_mapping(
            input=input, tools=tools, kwargs=kwargs, local_vars=local_vars
        )

        #########################################################
        # Native MCP Responses API
        #########################################################
        _mcp_dispatch = _responses_try_dispatch_mcp_gateway(
            tools=tools,
            input=input,
            model=model,
            include=include,
            instructions=instructions,
            max_output_tokens=max_output_tokens,
            prompt=prompt,
            metadata=metadata,
            parallel_tool_calls=parallel_tool_calls,
            previous_response_id=previous_response_id,
            reasoning=reasoning,
            store=store,
            background=background,
            stream=stream,
            temperature=temperature,
            text=text,
            tool_choice=tool_choice,
            top_p=top_p,
            truncation=truncation,
            user=user,
            extra_headers=extra_headers,
            extra_query=extra_query,
            extra_body=extra_body,
            timeout=timeout,
            custom_llm_provider=custom_llm_provider,
            kwargs=kwargs,
            _is_async=_is_async,
        )
        if _mcp_dispatch is not None:
            return _mcp_dispatch

        # get provider config
        responses_api_provider_config: Optional[BaseResponsesAPIConfig]
        if custom_llm_provider is None:
            responses_api_provider_config = None
        else:
            responses_api_provider_config = (
                ProviderConfigManager.get_provider_responses_api_config(
                    model=model,
                    provider=custom_llm_provider,
                )
            )

        local_vars.update(kwargs)
        if reasoning is None and "reasoning_effort" in local_vars:
            _mapped = LiteLLMResponsesTransformationHandler()._map_reasoning_effort(
                local_vars.pop("reasoning_effort")
            )
            if _mapped is not None:
                reasoning = _mapped
                local_vars["reasoning"] = _mapped
        # Get ResponsesAPIOptionalRequestParams with only valid parameters
        response_api_optional_params: ResponsesAPIOptionalRequestParams = (
            ResponsesAPIRequestUtils.get_requested_response_api_optional_param(
                local_vars
            )
        )

        _file_search_dispatch = _responses_try_dispatch_emulated_file_search(
            tools=tools,
            input=input,
            model=model,
            responses_api_provider_config=responses_api_provider_config,
            use_chat_completions_api=use_chat_completions_api,
            include=include,
            instructions=instructions,
            max_output_tokens=max_output_tokens,
            prompt=prompt,
            metadata=metadata,
            parallel_tool_calls=parallel_tool_calls,
            previous_response_id=previous_response_id,
            reasoning=reasoning,
            store=store,
            background=background,
            stream=stream,
            temperature=temperature,
            text=text,
            tool_choice=tool_choice,
            top_p=top_p,
            truncation=truncation,
            user=user,
            service_tier=service_tier,
            safety_identifier=safety_identifier,
            text_format=text_format,
            allowed_openai_params=allowed_openai_params,
            extra_headers=extra_headers,
            extra_query=extra_query,
            extra_body=extra_body,
            timeout=timeout,
            custom_llm_provider=custom_llm_provider,
            kwargs=kwargs,
            _is_async=_is_async,
        )
        if _file_search_dispatch is not None:
            return _file_search_dispatch

        if responses_api_provider_config is None or use_chat_completions_api is True:
            return litellm_completion_transformation_handler.api_handler(
                model=model,
                input=input,
                responses_api_request=response_api_optional_params,
                custom_llm_provider=custom_llm_provider,
                _is_async=_is_async,
                stream=stream,
                extra_headers=extra_headers,
                extra_body=extra_body,
                timeout=timeout if timeout is not None else request_timeout,
                **kwargs,
            )

        # Get optional parameters for the responses API
        responses_api_request_params: Dict = (
            ResponsesAPIRequestUtils.get_optional_params_responses_api(
                model=model,
                responses_api_provider_config=responses_api_provider_config,
                response_api_optional_params=response_api_optional_params,
                allowed_openai_params=allowed_openai_params,
            )
        )

        litellm_logging_obj.update_from_kwargs(
            kwargs=kwargs,
            model=model,
            user=user,
            optional_params=dict(responses_api_request_params),
            litellm_params={
                **responses_api_request_params,
                "aresponses": _is_async,
                "litellm_call_id": litellm_call_id,
                "model_info": kwargs.get("model_info"),
                "data_residency": infer_openai_data_residency(
                    custom_llm_provider, litellm_params.api_base
                ),
                "metadata": (
                    kwargs["litellm_metadata"]
                    if "litellm_metadata" in kwargs
                    else kwargs.get("metadata")
                ),
            },
            custom_llm_provider=custom_llm_provider,
        )

        # Decode any litellm-encoded encrypted-content item IDs back to their original IDs
        input = ResponsesAPIRequestUtils._restore_encrypted_content_item_ids_in_input(input)

        # Call the handler with _is_async flag instead of directly calling the async handler
        if custom_llm_provider is None:
            raise ValueError("custom_llm_provider is required but passed as None")

        response = api_handler.api_handler(
            model=model,
            input=input,
            responses_api_provider_config=responses_api_provider_config,
            response_api_optional_request_params=responses_api_request_params,
            custom_llm_provider=custom_llm_provider,
            litellm_params=litellm_params,
            logging_obj=litellm_logging_obj,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout or request_timeout,
            _is_async=_is_async,
            client=kwargs.get("client"),
            fake_stream=responses_api_provider_config.should_fake_stream(
                model=model, stream=stream, custom_llm_provider=custom_llm_provider
            ),
            litellm_metadata=kwargs.get("litellm_metadata", {}),
            shared_session=kwargs.get("shared_session"),
        )

        # Update the responses_api_response_id with the model_id
        if isinstance(response, ResponsesAPIResponse):
            response = ResponsesAPIRequestUtils._update_responses_api_response_id_with_model_id(
                responses_api_response=response,
                litellm_metadata=kwargs.get("litellm_metadata", {}),
                custom_llm_provider=custom_llm_provider,
            )
            # Stamp custom_llm_provider so callbacks can identify the provider
            # (mirrors litellm/main.py:1371 for chat completions)
            response._hidden_params["custom_llm_provider"] = custom_llm_provider

        return response
    except Exception as e:
        raise config.exception_type(
            model=model,
            custom_llm_provider=custom_llm_provider,
            original_exception=e,
            completion_kwargs=local_vars,
            extra_kwargs=kwargs,
        )

@client
def delete_responses(
    response_id: str,
    # Use the following arguments if you need to pass additional parameters to the API that aren't available via kwargs.
    # The extra values given here take precedence over values defined on the client or passed to this method.
    extra_headers: Optional[Dict[str, Any]] = None,
    extra_query: Optional[Dict[str, Any]] = None,
    extra_body: Optional[Dict[str, Any]] = None,
    timeout: Optional[Union[float, httpx.Timeout]] = None,
    # LiteLLM specific params,
    custom_llm_provider: Optional[str] = None,
    **kwargs,
) -> Union[DeleteResponseResult, Coroutine[Any, Any, DeleteResponseResult]]:
    """
    Synchronous version of the DELETE Responses API

    DELETE /v1/responses/{response_id} endpoint in the responses API

    """
    local_vars = locals()
    try:
        litellm_logging_obj: LiteLLMLoggingObj = kwargs.get("litellm_logging_obj")  # type: ignore
        litellm_call_id: Optional[str] = kwargs.get("litellm_call_id", None)
        _is_async = kwargs.pop("adelete_responses", False) is True

        # get llm provider logic
        litellm_params = GenericLiteLLMParams(**kwargs)

        # get custom llm provider from response_id
        decoded_response_id: DecodedResponseId = ResponseIdentityManager._decode_responses_api_response_id(response_id=response_id)
        response_id = decoded_response_id.get("response_id") or response_id
        custom_llm_provider = (
            decoded_response_id.get("custom_llm_provider") or custom_llm_provider
        )

        if custom_llm_provider is None:
            raise ValueError("custom_llm_provider is required but passed as None")

        # get provider config
        responses_api_provider_config: Optional[BaseResponsesAPIConfig] = (
            ProviderConfigManager.get_provider_responses_api_config(
                model=None,
                provider=custom_llm_provider,
            )
        )

        if responses_api_provider_config is None:
            raise ValueError(
                f"DELETE responses is not supported for {custom_llm_provider}"
            )

        local_vars.update(kwargs)

        # Pre Call logging
        litellm_logging_obj.update_from_kwargs(
            kwargs=local_vars,
            model=None,
            optional_params={
                "response_id": response_id,
            },
            litellm_params={
                "litellm_call_id": litellm_call_id,
            },
            custom_llm_provider=custom_llm_provider,
        )

        # Call the handler with _is_async flag instead of directly calling the async handler
        response = api_handler.delete_api_handler(
            response_id=response_id,
            custom_llm_provider=custom_llm_provider,
            responses_api_provider_config=responses_api_provider_config,
            litellm_params=litellm_params,
            logging_obj=litellm_logging_obj,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout or request_timeout,
            _is_async=_is_async,
            client=kwargs.get("client"),
            shared_session=kwargs.get("shared_session"),
        )

        return response
    except Exception as e:
        raise config.exception_type(
            model=None,
            custom_llm_provider=custom_llm_provider,
            original_exception=e,
            completion_kwargs=local_vars,
            extra_kwargs=kwargs,
        )

@client
def get_responses(
    response_id: str,
    # Use the following arguments if you need to pass additional parameters to the API that aren't available via kwargs.
    # The extra values given here take precedence over values defined on the client or passed to this method.
    extra_headers: Optional[Dict[str, Any]] = None,
    extra_query: Optional[Dict[str, Any]] = None,
    extra_body: Optional[Dict[str, Any]] = None,
    timeout: Optional[Union[float, httpx.Timeout]] = None,
    # LiteLLM specific params,
    custom_llm_provider: Optional[str] = None,
    **kwargs,
) -> Union[ResponsesAPIResponse, Coroutine[Any, Any, ResponsesAPIResponse]]:
    """
    Fetch a response by its ID.

    GET /v1/responses/{response_id} endpoint in the responses API

    Args:
        response_id: The ID of the response to fetch.
        custom_llm_provider: Optional provider name. If not specified, will be decoded from response_id.

    Returns:
        The response object with complete information about the stored response.
    """
    local_vars = locals()
    try:
        litellm_logging_obj: LiteLLMLoggingObj = kwargs.get("litellm_logging_obj")  # type: ignore
        litellm_call_id: Optional[str] = kwargs.get("litellm_call_id", None)
        _is_async = kwargs.pop("aget_responses", False) is True

        # get llm provider logic
        litellm_params = GenericLiteLLMParams(**kwargs)

        # get custom llm provider from response_id
        decoded_response_id: DecodedResponseId = ResponseIdentityManager._decode_responses_api_response_id(response_id=response_id)
        response_id = decoded_response_id.get("response_id") or response_id
        custom_llm_provider = (
            decoded_response_id.get("custom_llm_provider") or custom_llm_provider
        )

        if custom_llm_provider is None:
            raise ValueError("custom_llm_provider is required but passed as None")

        # get provider config
        responses_api_provider_config: Optional[BaseResponsesAPIConfig] = (
            ProviderConfigManager.get_provider_responses_api_config(
                model=None,
                provider=custom_llm_provider,
            )
        )

        if responses_api_provider_config is None:
            raise ValueError(
                f"GET responses is not supported for {custom_llm_provider}"
            )

        local_vars.update(kwargs)

        # Pre Call logging
        litellm_logging_obj.update_from_kwargs(
            kwargs=local_vars,
            model=None,
            optional_params={
                "response_id": response_id,
            },
            litellm_params={
                "litellm_call_id": litellm_call_id,
            },
            custom_llm_provider=custom_llm_provider,
        )

        # Call the handler with _is_async flag instead of directly calling the async handler
        response = api_handler.get_responses(
            response_id=response_id,
            custom_llm_provider=custom_llm_provider,
            responses_api_provider_config=responses_api_provider_config,
            litellm_params=litellm_params,
            logging_obj=litellm_logging_obj,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout or request_timeout,
            _is_async=_is_async,
            client=kwargs.get("client"),
            shared_session=kwargs.get("shared_session"),
        )

        # Update the responses_api_response_id with the model_id
        if isinstance(response, ResponsesAPIResponse):
            response = ResponsesAPIRequestUtils._update_responses_api_response_id_with_model_id(
                responses_api_response=response,
                litellm_metadata=kwargs.get("litellm_metadata", {}),
                custom_llm_provider=custom_llm_provider,
            )

        return response
    except Exception as e:
        raise config.exception_type(
            model=None,
            custom_llm_provider=custom_llm_provider,
            original_exception=e,
            completion_kwargs=local_vars,
            extra_kwargs=kwargs,
        )

@client
def list_input_items(
    response_id: str,
    after: Optional[str] = None,
    before: Optional[str] = None,
    include: Optional[List[str]] = None,
    limit: int = 20,
    order: Literal["asc", "desc"] = "desc",
    extra_headers: Optional[Dict[str, Any]] = None,
    timeout: Optional[Union[float, httpx.Timeout]] = None,
    custom_llm_provider: Optional[str] = None,
    **kwargs,
) -> Union[Dict, Coroutine[Any, Any, Dict]]:
    """List input items for a response"""
    local_vars = locals()
    try:
        litellm_logging_obj: LiteLLMLoggingObj = kwargs.get("litellm_logging_obj")  # type: ignore
        litellm_call_id: Optional[str] = kwargs.get("litellm_call_id", None)
        _is_async = kwargs.pop("alist_input_items", False) is True

        litellm_params = GenericLiteLLMParams(**kwargs)

        decoded_response_id = ResponseIdentityManager._decode_responses_api_response_id(response_id=response_id)
        response_id = decoded_response_id.get("response_id") or response_id
        custom_llm_provider = (
            decoded_response_id.get("custom_llm_provider") or custom_llm_provider
        )

        if custom_llm_provider is None:
            raise ValueError("custom_llm_provider is required but passed as None")

        responses_api_provider_config: Optional[BaseResponsesAPIConfig] = (
            ProviderConfigManager.get_provider_responses_api_config(
                model=None,
                provider=custom_llm_provider,
            )
        )

        if responses_api_provider_config is None:
            raise ValueError(
                f"list_input_items is not supported for {custom_llm_provider}"
            )

        local_vars.update(kwargs)

        litellm_logging_obj.update_from_kwargs(
            kwargs=local_vars,
            model=None,
            optional_params={"response_id": response_id},
            litellm_params={"litellm_call_id": litellm_call_id},
            custom_llm_provider=custom_llm_provider,
        )

        response = api_handler.list_responses_input_items(
            response_id=response_id,
            custom_llm_provider=custom_llm_provider,
            responses_api_provider_config=responses_api_provider_config,
            litellm_params=litellm_params,
            logging_obj=litellm_logging_obj,
            after=after,
            before=before,
            include=include,
            limit=limit,
            order=order,
            extra_headers=extra_headers,
            timeout=timeout or request_timeout,
            _is_async=_is_async,
            client=kwargs.get("client"),
            shared_session=kwargs.get("shared_session"),
        )

        return response
    except Exception as e:
        raise config.exception_type(
            model=None,
            custom_llm_provider=custom_llm_provider,
            original_exception=e,
            completion_kwargs=local_vars,
            extra_kwargs=kwargs,
        )

@client
def cancel_responses(
    response_id: str,
    # Use the following arguments if you need to pass additional parameters to the API that aren't available via kwargs.
    # The extra values given here take precedence over values defined on the client or passed to this method.
    extra_headers: Optional[Dict[str, Any]] = None,
    extra_query: Optional[Dict[str, Any]] = None,
    extra_body: Optional[Dict[str, Any]] = None,
    timeout: Optional[Union[float, httpx.Timeout]] = None,
    # LiteLLM specific params,
    custom_llm_provider: Optional[str] = None,
    **kwargs,
) -> Union[ResponsesAPIResponse, Coroutine[Any, Any, ResponsesAPIResponse]]:
    """
    Synchronous version of the POST Responses API

    POST /v1/responses/{response_id}/cancel endpoint in the responses API

    """
    local_vars = locals()
    try:
        litellm_logging_obj: LiteLLMLoggingObj = kwargs.get("litellm_logging_obj")  # type: ignore
        litellm_call_id: Optional[str] = kwargs.get("litellm_call_id", None)
        _is_async = kwargs.pop("acancel_responses", False) is True

        # get llm provider logic
        litellm_params = GenericLiteLLMParams(**kwargs)

        # get custom llm provider from response_id
        decoded_response_id: DecodedResponseId = ResponseIdentityManager._decode_responses_api_response_id(response_id=response_id)
        response_id = decoded_response_id.get("response_id") or response_id
        custom_llm_provider = (
            decoded_response_id.get("custom_llm_provider") or custom_llm_provider
        )

        if custom_llm_provider is None:
            raise ValueError("custom_llm_provider is required but passed as None")

        # get provider config
        responses_api_provider_config: Optional[BaseResponsesAPIConfig] = (
            ProviderConfigManager.get_provider_responses_api_config(
                model=None,
                provider=custom_llm_provider,
            )
        )

        if responses_api_provider_config is None:
            raise ValueError(
                f"CANCEL responses is not supported for {custom_llm_provider}"
            )

        local_vars.update(kwargs)

        # Pre Call logging
        litellm_logging_obj.update_from_kwargs(
            kwargs=local_vars,
            model=None,
            optional_params={
                "response_id": response_id,
            },
            litellm_params={
                "litellm_call_id": litellm_call_id,
            },
            custom_llm_provider=custom_llm_provider,
        )

        # Call the handler with _is_async flag instead of directly calling the async handler
        response = api_handler.cancel_api_handler(
            response_id=response_id,
            custom_llm_provider=custom_llm_provider,
            responses_api_provider_config=responses_api_provider_config,
            litellm_params=litellm_params,
            logging_obj=litellm_logging_obj,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout or request_timeout,
            _is_async=_is_async,
            client=kwargs.get("client"),
            shared_session=kwargs.get("shared_session"),
        )

        return response
    except Exception as e:
        raise config.exception_type(
            model=None,
            custom_llm_provider=custom_llm_provider,
            original_exception=e,
            completion_kwargs=local_vars,
            extra_kwargs=kwargs,
        )

@client
def compact_responses(
    input: Union[str, ResponseInputParam],
    model: str,
    instructions: Optional[str] = None,
    previous_response_id: Optional[str] = None,
    extra_headers: Optional[Dict[str, Any]] = None,
    extra_query: Optional[Dict[str, Any]] = None,
    extra_body: Optional[Dict[str, Any]] = None,
    timeout: Optional[Union[float, httpx.Timeout]] = None,
    custom_llm_provider: Optional[str] = None,
    **kwargs,
) -> Union[ResponsesAPIResponse, Coroutine[Any, Any, ResponsesAPIResponse]]:
    local_vars = locals()
    try:
        litellm_logging_obj: LiteLLMLoggingObj = kwargs.get("litellm_logging_obj")  # type: ignore
        litellm_call_id: Optional[str] = kwargs.get("litellm_call_id", None)
        _is_async = kwargs.pop("acompact_responses", False) is True

        # get llm provider logic
        litellm_params = GenericLiteLLMParams(**kwargs)

        (
            model,
            custom_llm_provider,
            dynamic_api_key,
            dynamic_api_base,
        ) = litellm.get_llm_provider(
            model=model,
            custom_llm_provider=custom_llm_provider,
            api_base=litellm_params.api_base,
            api_key=litellm_params.api_key,
        )

        # Update local_vars with detected provider (fixes #19782)
        local_vars["custom_llm_provider"] = custom_llm_provider

        # Use dynamic credentials from get_llm_provider (e.g., when use_litellm_proxy=True)
        if dynamic_api_key is not None:
            litellm_params.api_key = dynamic_api_key
        if dynamic_api_base is not None:
            litellm_params.api_base = dynamic_api_base

        if custom_llm_provider is None:
            raise ValueError("custom_llm_provider is required but passed as None")

        # get provider config
        responses_api_provider_config: Optional[BaseResponsesAPIConfig] = (
            ProviderConfigManager.get_provider_responses_api_config(
                model=model,
                provider=custom_llm_provider,
            )
        )

        if responses_api_provider_config is None:
            raise ValueError(
                f"COMPACT responses is not supported for {custom_llm_provider}"
            )

        local_vars.update(kwargs)

        # Build optional params for compact endpoint
        response_api_optional_params: ResponsesAPIOptionalRequestParams = ResponsesAPIRequestUtils.get_requested_response_api_optional_param(local_vars)
        responses_api_request_params: Dict = (
            ResponsesAPIRequestUtils.get_optional_params_responses_api(
                model=model,
                responses_api_provider_config=responses_api_provider_config,
                response_api_optional_params=response_api_optional_params,
                allowed_openai_params=None,
            )
        )

        # Pre Call logging
        litellm_logging_obj.update_from_kwargs(
            kwargs=local_vars,
            model=model,
            optional_params=dict(responses_api_request_params),
            litellm_params={
                **responses_api_request_params,
                "litellm_call_id": litellm_call_id,
                "data_residency": infer_openai_data_residency(
                    custom_llm_provider, litellm_params.api_base
                ),
            },
            custom_llm_provider=custom_llm_provider,
        )

        # Decode any litellm-encoded encrypted-content item IDs back to their original IDs
        # before forwarding to the upstream provider.
        input = ResponsesAPIRequestUtils._restore_encrypted_content_item_ids_in_input(
            input
        )

        # Call the handler with _is_async flag instead of directly calling the async handler
        response = api_handler.compact_api_handler(
            model=model,
            input=input,
            responses_api_provider_config=responses_api_provider_config,
            response_api_optional_request_params=responses_api_request_params,
            litellm_params=litellm_params,
            logging_obj=litellm_logging_obj,
            custom_llm_provider=custom_llm_provider,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout or request_timeout,
            _is_async=_is_async,
            client=kwargs.get("client"),
            shared_session=kwargs.get("shared_session"),
        )

        # Update the responses_api_response_id with the model_id
        if isinstance(response, ResponsesAPIResponse):
            response = ResponsesAPIRequestUtils._update_responses_api_response_id_with_model_id(
                responses_api_response=response,
                litellm_metadata=kwargs.get("litellm_metadata", {}),
                custom_llm_provider=custom_llm_provider,
            )

        return response
    except Exception as e:
        raise config.exception_type(
            model=model,
            custom_llm_provider=custom_llm_provider,
            original_exception=e,
            completion_kwargs=local_vars,
            extra_kwargs=kwargs,
        )