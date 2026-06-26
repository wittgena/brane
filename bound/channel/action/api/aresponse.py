# bound.channel.action.api.aresponse
## @lineage: bound.channel.bridge.api.aresponse
import asyncio
import contextvars
from functools import partial
from typing import Any, Coroutine, Dict, Iterable, List, Literal, Optional, Type, Union, cast
import httpx
from pydantic import BaseModel

from anchor.switch.config.resolver import config
from bound.adapter.legacy.mcp.payload import MCPPayloadUtils
from bound.adapter.legacy.mcp.stream import create_mcp_list_tools_events, MCPEnhancedStreamingIterator
from bound.adapter.legacy.llm.types.response import *
from bound.adapter.legacy.llm.types.router import GenericLiteLLMParams
from bound.adapter.legacy.llm.openai.types import ResponseText
from bound.adapter.legacy.llm.openai.types import (
    AllMessageValues, PromptObject, Reasoning, ResponseIncludable, ResponseInputParam,
    ResponsesAPIResponse, ToolChoice, ToolParam,
)

from anchor.surface.model.provider.manager import ProviderConfigManager
from anchor.surface.model.provider.types import ProviderTypes
from anchor.switch.model.llm.provider import get_llm_provider

from bound.channel.action.param.litellm import get_litellm_params, infer_openai_data_residency
from bound.channel.response.config import BaseResponsesAPIConfig
from bound.channel.client.ws import ResponseWebsocketHandler
from bound.channel.client.wrapper import client
from bound.channel.response.identity import ResponseIdentityManager

from bound.channel.action.api.handler import ResponseApiHandler
from bound.channel.action.api.response import responses
from bound.channel.action.api.response_crud import delete_responses, get_responses, list_input_items, cancel_responses, compact_responses

from bound.broker.transport.stream.iterator import BaseResponsesAPIStreamingIterator
from bound.xor.secret.manager import get_secret_str

from arch.proto.phase.gate import uuid
from watcher.plane.emitter import get_emitter

log = get_emitter("api.aresponse")
LiteLLMLoggingObj = Any
ws_handler = ResponseWebsocketHandler()

async def _execute_sync_via_threadpool(func: Any, *args, **kwargs) -> Any:
    """동기(Sync) 브레인 파이프라인을 스레드 풀에서 안전하게 실행하는 공통 래퍼"""
    loop = asyncio.get_event_loop()
    ctx = contextvars.copy_context()
    func_with_context = partial(ctx.run, func, *args, **kwargs)
    
    init_response = await loop.run_in_executor(None, func_with_context)
    if asyncio.iscoroutine(init_response):
        return await init_response
    return init_response


@client
async def adelete_responses(response_id: str, **kwargs) -> DeleteResponseResult:
    kwargs["adelete_responses"] = True
    return await _execute_sync_via_threadpool(delete_responses, response_id=response_id, **kwargs)

@client
async def aget_responses(response_id: str, **kwargs) -> ResponsesAPIResponse:
    kwargs["aget_responses"] = True
    return await _execute_sync_via_threadpool(get_responses, response_id=response_id, **kwargs)

@client
async def alist_input_items(response_id: str, **kwargs) -> Dict:
    kwargs["alist_input_items"] = True
    return await _execute_sync_via_threadpool(list_input_items, response_id=response_id, **kwargs)

@client
async def acancel_responses(response_id: str, **kwargs) -> ResponsesAPIResponse:
    kwargs["acancel_responses"] = True
    return await _execute_sync_via_threadpool(cancel_responses, response_id=response_id, **kwargs)

@client
async def acompact_responses(input: Union[str, ResponseInputParam], model: str, **kwargs) -> ResponsesAPIResponse:
    kwargs["acompact_responses"] = True
    return await _execute_sync_via_threadpool(compact_responses, input=input, model=model, **kwargs)


# =====================================================================
# 3. 메인 aresponses (비동기 프롬프트 관리 + 퍼사드)
# =====================================================================
@client
async def aresponses(
    input: Union[str, ResponseInputParam], model: str, **kwargs
) -> Union[ResponsesAPIResponse, BaseResponsesAPIStreamingIterator]:
    kwargs["aresponses"] = True
    
    # 3.1 비동기 전용 Prompt Management 훅 처리 (필요시)
    litellm_logging_obj = kwargs.get("litellm_logging_obj")
    prompt_id = kwargs.get("prompt_id")
    
    if isinstance(litellm_logging_obj, LiteLLMLoggingObj) and litellm_logging_obj.should_run_prompt_management_hooks(
        prompt_id=prompt_id, non_default_params=kwargs
    ):
        client_input: List[AllMessageValues] = [{"role": "user", "content": input}] if isinstance(input, str) else [
            item for item in input if isinstance(item, dict) and "role" in item # type: ignore[misc]
        ]
        model, merged_input, merged_optional_params = await litellm_logging_obj.async_get_chat_completion_prompt(
            model=model, messages=client_input, non_default_params=kwargs,
            prompt_id=prompt_id, prompt_variables=kwargs.get("prompt_variables"),
            prompt_label=kwargs.get("prompt_label"), prompt_version=kwargs.get("prompt_version"),
        )
        input = cast(Union[str, ResponseInputParam], merged_input)
        kwargs.pop("prompt_id", None)
        kwargs["_async_prompt_merged_params"] = merged_optional_params

    # 3.2 전처리가 끝난 후 동기 파이프라인(responses)으로 위임
    return await _execute_sync_via_threadpool(responses, input=input, model=model, **kwargs)


# =====================================================================
# 4. MCP 및 WebSocket 워크플로우 (유지)
# =====================================================================
def _has_file_search_tool(tools: Optional[Any]) -> bool:
    if not tools: return False
    return any(isinstance(t, dict) and t.get("type") == "file_search" for t in tools)

async def aresponses_api_with_mcp(input: Union[str, ResponseInputParam], model: str, tools: Optional[Iterable[ToolParam]] = None, stream: Optional[bool] = None, previous_response_id: Optional[str] = None, **kwargs) -> Union[ResponsesAPIResponse, BaseResponsesAPIStreamingIterator]:
    """MCP 오케스트레이션 워크플로우 (멀티 턴)"""
    from bound.adapter.legacy.mcp.handler import LegacyMCPHandler
    mcp_tools_with_litellm_proxy, other_tools = MCPPayloadUtils._parse_mcp_tools(tools)
    user_api_key_auth = kwargs.get("user_api_key_auth") or kwargs.get("litellm_metadata", {}).get("user_api_key_auth")

    mcp_auth_header, mcp_server_auth_headers = None, None
    if secret_fields := kwargs.get("secret_fields"):
        mcp_auth_header, mcp_server_auth_headers, _, _ = ResponseIdentityManager.extract_mcp_headers_from_request(secret_fields=secret_fields, tools=tools)

    original_mcp_tools, tool_server_map = await LegacyMCPHandler._process_mcp_tools_without_openai_transform(
        user_api_key_auth=user_api_key_auth, mcp_tools_with_litellm_proxy=mcp_tools_with_litellm_proxy,
        litellm_trace_id=kwargs.get("litellm_trace_id"), mcp_auth_header=mcp_auth_header, mcp_server_auth_headers=mcp_server_auth_headers,
    )
    openai_tools = LegacyMCPHandler._transform_mcp_tools_to_openai(original_mcp_tools)
    all_tools = openai_tools + other_tools if (openai_tools or other_tools) else None
    
    call_params = {"stream": stream, "previous_response_id": previous_response_id, **kwargs}

    if stream and mcp_tools_with_litellm_proxy:
        mcp_discovery_events = await create_mcp_list_tools_events(
            mcp_tools_with_litellm_proxy=mcp_tools_with_litellm_proxy, user_api_key_auth=user_api_key_auth,
            base_item_id=f"mcp_{uuid.uuid4().hex[:8]}", pre_processed_mcp_tools=original_mcp_tools,
        )
        return LegacyMCPHandler._create_mcp_streaming_response(
            input=input, model=model, all_tools=all_tools, mcp_tools_with_litellm_proxy=mcp_tools_with_litellm_proxy,
            mcp_discovery_events=mcp_discovery_events, call_params=call_params, previous_response_id=previous_response_id,
            tool_server_map=tool_server_map, **kwargs,
        )

    should_auto_execute = bool(mcp_tools_with_litellm_proxy) and LegacyMCPHandler._should_auto_execute_tools(mcp_tools_with_litellm_proxy=mcp_tools_with_litellm_proxy)
    initial_call_params = MCPPayloadUtils._prepare_initial_call_params(call_params=call_params, should_auto_execute=should_auto_execute)

    response = await aresponses(input=input, model=model, tools=all_tools, previous_response_id=previous_response_id, **initial_call_params)
    if should_auto_execute and isinstance(response, ResponsesAPIResponse) and (tool_calls := MCPPayloadUtils._extract_tool_calls_from_response(response)):
        tool_results = await LegacyMCPHandler._execute_tool_calls(
            tool_server_map=tool_server_map, tool_calls=tool_calls, user_api_key_auth=user_api_key_auth,
            mcp_auth_header=mcp_auth_header, mcp_server_auth_headers=mcp_server_auth_headers,
            oauth2_headers=None, raw_headers=None, litellm_call_id=kwargs.get("litellm_call_id"), litellm_trace_id=kwargs.get("litellm_trace_id"),
        )
        if tool_results:
            follow_up_input = MCPPayloadUtils._create_follow_up_input(response=response, tool_results=tool_results, original_input=input)
            follow_up_call_params = MCPPayloadUtils._prepare_follow_up_call_params(call_params=call_params, original_stream_setting=stream or False)
            final_response = await LegacyMCPHandler._make_follow_up_call(follow_up_input=follow_up_input, model=model, all_tools=all_tools, response_id=response.id, **follow_up_call_params)
            
            if not stream and isinstance(final_response, ResponsesAPIResponse):
                mcp_tools_for_output, _ = await LegacyMCPHandler._process_mcp_tools_without_openai_transform(
                    user_api_key_auth=user_api_key_auth, mcp_tools_with_litellm_proxy=mcp_tools_with_litellm_proxy,
                    mcp_auth_header=mcp_auth_header, mcp_server_auth_headers=mcp_server_auth_headers,
                )
                final_response = MCPPayloadUtils._add_mcp_output_elements_to_response(response=final_response, mcp_tools_fetched=mcp_tools_for_output, tool_results=tool_results)
            return final_response
    return response

@client
async def _aresponses_websocket(
    model: str,
    websocket: Any,
    api_base: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout: Optional[float] = None,
    **kwargs,
):
    litellm_logging_obj: LiteLLMLoggingObj = kwargs.get("litellm_logging_obj")  # type: ignore
    user = kwargs.get("user", None)
    litellm_params = GenericLiteLLMParams(**kwargs)
    litellm_params_dict = get_litellm_params(**kwargs)

    (
        model,
        _custom_llm_provider,
        dynamic_api_key,
        dynamic_api_base,
    ) = get_llm_provider(
        model=model,
        api_base=api_base,
        api_key=api_key,
    )

    litellm_params_dict["data_residency"] = infer_openai_data_residency(
        _custom_llm_provider,
        dynamic_api_base or litellm_params.api_base or config.api_base,
    )

    litellm_logging_obj.update_from_kwargs(
        kwargs=kwargs,
        model=model,
        user=user,
        optional_params={},
        litellm_params=litellm_params_dict,
        custom_llm_provider=_custom_llm_provider,
    )

    responses_api_provider_config: Optional[BaseResponsesAPIConfig] = None
    if _custom_llm_provider is not None:
        responses_api_provider_config = (
            ProviderConfigManager.get_provider_responses_api_config(
                model=model,
                provider=ProviderTypes(_custom_llm_provider),
            )
        )

    resolved_api_base = (
        dynamic_api_base or litellm_params.api_base or configapi_base or None
    )
    resolved_api_key = (
        dynamic_api_key
        or litellm_params.api_key
        or config.api_key
        or config.openai_key
        or get_secret_str("OPENAI_API_KEY")
    )

    # Extract params that we're passing explicitly to avoid duplicates in **kwargs
    _explicit_keys = {
        "user_api_key_dict",
        "litellm_metadata",
        "custom_llm_provider",
        "model",
        "websocket",
        "litellm_logging_obj",
        "api_base",
        "api_key",
        "timeout",
    }
    remaining_kwargs = {k: v for k, v in kwargs.items() if k not in _explicit_keys}
    await ws_handler.async_responses_websocket(
        model=model,
        websocket=websocket,
        logging_obj=litellm_logging_obj,
        responses_api_provider_config=responses_api_provider_config,
        api_base=resolved_api_base,
        api_key=resolved_api_key,
        timeout=timeout,
        user_api_key_dict=kwargs.get("user_api_key_dict"),
        litellm_metadata=_build_litellm_metadata_for_ws(kwargs),
        custom_llm_provider=_custom_llm_provider,
        **remaining_kwargs,
    )
