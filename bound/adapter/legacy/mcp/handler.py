# bound.adapter.legacy.mcp.handler
## @lineage: anchor.surface.legacy.proxy.handler
import re
from datetime import datetime
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    Iterable,
    List,
    Literal,
    Optional,
    Tuple,
    Union,
)
from fastapi import HTTPException

from anchor.surface.exception import BlockedPiiEntityError, GuardrailRaisedException
from anchor.switch.params import ResponsesAPIResponse
from anchor.surface.legacy.llm.types.utils import CallTypes, StandardLoggingMCPToolCall

from anchor.surface.legacy.proxy.reverse import global_mcp_server_manager, LegacyLitellmToolsManager
from anchor.surface.legacy.proxy.logger import LegacyLogManager
from anchor.surface.legacy.mcp.tool import transform_mcp_tool_to_openai_responses_api_tool, transform_mcp_tool_to_openai_tool
from anchor.surface.legacy.mcp.payload import MCPPayloadUtils
from bound.transport.stream.iterator import BaseResponsesAPIStreamingIterator

if TYPE_CHECKING:
    from mcp.types import Tool as MCPTool
else:
    MCPTool = Any

from arch.proto.phase.gate import uuid
from watcher.plane.emitter import get_emitter

log = get_emitter("proxy.mcp")

ToolParam = Any
LITELLM_PROXY_MCP_SERVER_URL = "litellm_proxy"
LITELLM_PROXY_MCP_SERVER_URL_PREFIX = f"{LITELLM_PROXY_MCP_SERVER_URL}/mcp/"
MCP_TOOL_PREFIX_SEPARATOR = "-"
_PROXY_MCP_PATH_RE = re.compile(r"^https?://.+/mcp/([^/]+)$")


def split_server_prefix_from_name(prefixed_name: str) -> Tuple[str, str]:
    if MCP_TOOL_PREFIX_SEPARATOR in prefixed_name:
        parts = prefixed_name.split(MCP_TOOL_PREFIX_SEPARATOR, 1)
        if len(parts) == 2:
            return parts[1], parts[0]
    return prefixed_name, ""


class LegacyMCPHandler:
    @staticmethod
    def _create_tool_execution_events(
        tool_calls: List[Any], tool_results: List[Dict[str, Any]]
    ) -> List[Any]:
        tool_execution_events: List[Any] = []

        for tool_result in tool_results:
            tool_call_id = tool_result.get("tool_call_id", "unknown")
            result_text = tool_result.get("result", "")

            tool_name = "unknown"
            tool_arguments = "{}"
            for tool_call in tool_calls:
                (
                    name,
                    args,
                    call_id,
                ) = MCPPayloadUtils._extract_tool_call_details(tool_call)
                if call_id == tool_call_id:
                    tool_name = name or "unknown"
                    tool_arguments = args or "{}"
                    break

            from anchor.surface.legacy.mcp.stream import create_mcp_call_events
            execution_events = create_mcp_call_events(
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                arguments=tool_arguments,
                result=result_text,
                base_item_id=f"mcp_{uuid.uuid4().hex[:8]}",
                sequence_start=len(tool_execution_events) + 1,
            )
            tool_execution_events.extend(execution_events)

        return tool_execution_events

    @staticmethod
    def _should_use_litellm_mcp_gateway(tools: Optional[Iterable[ToolParam]]) -> bool:
        if tools:
            for tool in tools:
                if isinstance(tool, dict) and tool.get("type") == "mcp":
                    server_url = tool.get("server_url", "")
                    if isinstance(server_url, str) and server_url.startswith(LITELLM_PROXY_MCP_SERVER_URL):
                        return True
                    if isinstance(server_url, str) and _PROXY_MCP_PATH_RE.match(server_url):
                        return True
        return False

    @staticmethod
    async def _get_mcp_tools_from_manager(
        user_api_key_auth: Any,
        mcp_tools_with_litellm_proxy: Optional[Iterable[ToolParam]],
        litellm_trace_id: Optional[str] = None,
        mcp_auth_header: Optional[str] = None,
        mcp_server_auth_headers: Optional[Dict[str, Dict[str, str]]] = None,
    ) -> tuple[List[MCPTool], List[str]]:
        mcp_servers: List[str] = []
        if mcp_tools_with_litellm_proxy:
            for _tool in mcp_tools_with_litellm_proxy:
                server_url = _tool.get("server_url", "") if isinstance(_tool, dict) else ""
                if isinstance(server_url, str) and server_url.startswith(LITELLM_PROXY_MCP_SERVER_URL_PREFIX):
                    mcp_servers.append(server_url.split("/")[-1])

        tools, server_names = await LegacyLitellmToolsManager.get_tools_from_manager(
            user_api_key_auth=user_api_key_auth,
            mcp_servers=mcp_servers,
            litellm_trace_id=litellm_trace_id,
            mcp_auth_header=mcp_auth_header,
            mcp_server_auth_headers=mcp_server_auth_headers
        )
        return tools, server_names

    @staticmethod
    def _deduplicate_mcp_tools(
        mcp_tools: List[MCPTool], allowed_mcp_servers: List[str]
    ) -> tuple[List[MCPTool], dict[str, str]]:
        seen_names = set()
        deduplicated_tools = []
        tool_server_map: dict[str, str] = {}

        for tool in mcp_tools:
            tool_name = tool.get("name") if isinstance(tool, dict) else getattr(tool, "name", None)

            if tool_name and tool_name not in seen_names:
                seen_names.add(tool_name)
                deduplicated_tools.append(tool)
                if len(allowed_mcp_servers) == 1:
                    tool_server_map[tool_name] = allowed_mcp_servers[0]
                else:
                    _, tool_server_map[tool_name] = split_server_prefix_from_name(tool_name)

        return deduplicated_tools, tool_server_map

    @staticmethod
    def _filter_mcp_tools_by_allowed_tools(
        mcp_tools: List[MCPTool], mcp_tools_with_litellm_proxy: List[ToolParam]
    ) -> List[MCPTool]:
        allowed_tool_names = set()
        for tool_config in mcp_tools_with_litellm_proxy:
            if isinstance(tool_config, dict) and "allowed_tools" in tool_config:
                allowed_tools = tool_config.get("allowed_tools", [])
                if isinstance(allowed_tools, list):
                    allowed_tool_names.update(allowed_tools)

        if not allowed_tool_names:
            return mcp_tools

        filtered_tools = []
        for mcp_tool in mcp_tools:
            tool_name = mcp_tool.get("name") if isinstance(mcp_tool, dict) else getattr(mcp_tool, "name", None)
            if not tool_name:
                continue

            if tool_name in allowed_tool_names:
                filtered_tools.append(mcp_tool)
                continue

            unprefixed_name, _ = split_server_prefix_from_name(tool_name)
            if unprefixed_name in allowed_tool_names:
                filtered_tools.append(mcp_tool)

        return filtered_tools

    @staticmethod
    async def _process_mcp_tools_to_openai_format(
        user_api_key_auth: Any,
        mcp_tools_with_litellm_proxy: List[ToolParam],
        litellm_trace_id: Optional[str] = None,
    ) -> tuple[List[Any], dict[str, str]]:
        (
            deduplicated_mcp_tools,
            tool_server_map,
        ) = await LegacyMCPHandler._process_mcp_tools_without_openai_transform(
            user_api_key_auth,
            mcp_tools_with_litellm_proxy,
            litellm_trace_id=litellm_trace_id,
        )

        openai_tools = LegacyMCPHandler._transform_mcp_tools_to_openai(deduplicated_mcp_tools)
        return openai_tools, tool_server_map

    @staticmethod
    async def _process_mcp_tools_without_openai_transform(
        user_api_key_auth: Any,
        mcp_tools_with_litellm_proxy: List[ToolParam],
        litellm_trace_id: Optional[str] = None,
        mcp_auth_header: Optional[str] = None,
        mcp_server_auth_headers: Optional[Dict[str, Dict[str, str]]] = None,
    ) -> tuple[List[Any], dict[str, str]]:
        if not mcp_tools_with_litellm_proxy:
            return [], {}

        (
            mcp_tools_fetched,
            allowed_mcp_servers,
        ) = await LegacyMCPHandler._get_mcp_tools_from_manager(
            user_api_key_auth=user_api_key_auth,
            mcp_tools_with_litellm_proxy=mcp_tools_with_litellm_proxy,
            litellm_trace_id=litellm_trace_id,
            mcp_auth_header=mcp_auth_header,
            mcp_server_auth_headers=mcp_server_auth_headers,
        )

        filtered_mcp_tools = LegacyMCPHandler._filter_mcp_tools_by_allowed_tools(
            mcp_tools=mcp_tools_fetched,
            mcp_tools_with_litellm_proxy=mcp_tools_with_litellm_proxy,
        )

        (
            deduplicated_mcp_tools,
            tool_server_map,
        ) = LegacyMCPHandler._deduplicate_mcp_tools(
            filtered_mcp_tools, allowed_mcp_servers
        )

        return deduplicated_mcp_tools, tool_server_map

    @staticmethod
    def _transform_mcp_tools_to_openai(
        mcp_tools: List[Any],
        target_format: Literal["responses", "chat"] = "responses",
    ) -> List[Any]:
        openai_tools: List[Any] = []
        for mcp_tool in mcp_tools:
            if target_format == "chat":
                openai_tool = transform_mcp_tool_to_openai_tool(mcp_tool)
            else:
                openai_tool = transform_mcp_tool_to_openai_responses_api_tool(mcp_tool)
            openai_tools.append(openai_tool)

        return openai_tools

    @staticmethod
    def _should_auto_execute_tools(
        mcp_tools_with_litellm_proxy: Union[List[Dict[str, Any]], List[ToolParam]],
    ) -> bool:
        for tool in mcp_tools_with_litellm_proxy:
            if isinstance(tool, dict):
                if tool.get("require_approval") == "never":
                    return True
            elif getattr(tool, "require_approval", None) == "never":
                return True
        return False

    @staticmethod
    async def _execute_tool_calls(  
        tool_server_map: dict[str, str],
        tool_calls: List[Any],
        user_api_key_auth: Any,
        mcp_auth_header: Optional[str] = None,
        mcp_server_auth_headers: Optional[Dict[str, Dict[str, str]]] = None,
        oauth2_headers: Optional[Dict[str, str]] = None,
        raw_headers: Optional[Dict[str, str]] = None,
        litellm_call_id: Optional[str] = None,
        litellm_trace_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Execute tool calls and return results."""
        tool_results = []
        
        for tool_call in tool_calls:
            try:
                (
                    tool_name,
                    tool_arguments,
                    tool_call_id,
                ) = MCPPayloadUtils._extract_tool_call_details(tool_call)

                if not tool_name:
                    log.warning(f"Tool call missing name: {tool_call}")
                    continue

                parsed_arguments = MCPPayloadUtils._parse_tool_arguments(tool_arguments)
                server_name = tool_server_map[tool_name]

                sanitized_tool_name = tool_name
                unprefixed_name, prefixed_server_name = split_server_prefix_from_name(tool_name)
                if prefixed_server_name and prefixed_server_name == server_name and unprefixed_name:
                    sanitized_tool_name = unprefixed_name

                start_time = datetime.now()
                logging_input = [{"role": "tool", "content": {"tool_name": sanitized_tool_name, "arguments": parsed_arguments}}]
                tool_logging_call_id = litellm_call_id or str(uuid.uuid4())
                
                logging_request_data = {
                    "model": f"MCP: {tool_name}",
                    "metadata": {
                        "tool_call_id": tool_call_id,
                        "tool_name": sanitized_tool_name,
                        "server_name": server_name,
                    },
                    "input": logging_input,
                    "call_type": CallTypes.call_mcp_tool.value,
                    "litellm_call_id": tool_logging_call_id,
                    "proxy_server_request": {
                        "url": "/mcp/tools/call",
                        "method": "POST",
                        "headers": {},
                        "body": {"name": sanitized_tool_name, "arguments": parsed_arguments},
                    },
                }

                if litellm_trace_id:
                    logging_request_data["litellm_trace_id"] = litellm_trace_id
                
                if user_api_key_auth is not None:
                    user_api_key = getattr(user_api_key_auth, "api_key", None)
                    if user_api_key:
                        logging_request_data["metadata"]["user_api_key"] = user_api_key

                    user_identifier = getattr(user_api_key_auth, "end_user_id", None) or getattr(user_api_key_auth, "user_id", None)
                    if user_identifier:
                        logging_request_data["user"] = user_identifier

                # === 1. 어댑터 호출: 로깅 셋업 및 pre_call ===
                litellm_logging_obj, logging_request_data = await LegacyLogManager.log_pre_call(
                    tool_name=tool_name,
                    logging_request_data=logging_request_data,
                    logging_input=logging_input,
                    start_time=start_time
                )

                if litellm_logging_obj:
                    # Tool Metadata 세팅
                    standard_logging_mcp_tool_call: StandardLoggingMCPToolCall = {
                        "name": sanitized_tool_name,
                        "arguments": parsed_arguments,
                        "namespaced_tool_name": tool_name,
                    }
                    mcp_server = global_mcp_server_manager._get_mcp_server_from_tool_name(tool_name)
                    if mcp_server:
                        mcp_info = getattr(mcp_server, "mcp_info", {}) or {}
                        standard_logging_mcp_tool_call["mcp_server_name"] = mcp_info.get("server_name") or getattr(mcp_server, "server_name", None) or server_name
                        if mcp_info.get("logo_url"):
                            standard_logging_mcp_tool_call["mcp_server_logo_url"] = mcp_info.get("logo_url")
                        if mcp_info.get("mcp_server_cost_info"):
                            standard_logging_mcp_tool_call["mcp_server_cost_info"] = mcp_info.get("mcp_server_cost_info")
                            
                    litellm_logging_obj.model_call_details["mcp_tool_call_metadata"] = standard_logging_mcp_tool_call
                    litellm_logging_obj.model = f"MCP: {tool_name}"
                    litellm_logging_obj.call_type = CallTypes.call_mcp_tool.value

                # === 2. 실제 MCP 툴 실행 ===
                result = await global_mcp_server_manager.call_tool(
                    server_name=server_name,
                    name=sanitized_tool_name,
                    arguments=parsed_arguments,
                    user_api_key_auth=user_api_key_auth,
                    mcp_auth_header=mcp_auth_header,
                    mcp_server_auth_headers=mcp_server_auth_headers,
                    oauth2_headers=oauth2_headers,
                    raw_headers=raw_headers,
                    # proxy_logging_obj=proxy_logging_obj (매니저 내부에서 처리되거나 더 이상 직접 넘기지 않음)
                )

                # === 3. 어댑터 호출: 성공 로깅 ===
                await LegacyLogManager.log_post_call_success(
                    litellm_logging_obj=litellm_logging_obj,
                    result=result,
                    start_time=start_time,
                    tool_name=tool_name
                )

                result_text = MCPPayloadUtils._parse_mcp_result(result)
                tool_results.append({"tool_call_id": tool_call_id, "result": result_text, "name": tool_name})

            # === 4. 어댑터 호출: 에러 로깅 (반복되는 catch 블록 통합) ===
            except BlockedPiiEntityError as e:
                await LegacyLogManager.log_failure(user_api_key_auth, logging_request_data, e)
                log.error(f"BlockedPiiEntityError in MCP tool call: {str(e)}")
                error_msg = f"Tool call blocked: PII entity '{getattr(e, 'entity_type', 'unknown')}' detected by guardrail '{getattr(e, 'guardrail_name', 'unknown')}'. {str(e)}"
                tool_results.append({"tool_call_id": tool_call_id, "result": error_msg, "name": tool_name})
                
            except GuardrailRaisedException as e:
                await LegacyLogManager.log_failure(user_api_key_auth, logging_request_data, e)
                log.error(f"GuardrailRaisedException in MCP tool call: {str(e)}")
                error_msg = f"Tool call blocked: Guardrail '{getattr(e, 'guardrail_name', 'unknown')}' violation. {str(e)}"
                tool_results.append({"tool_call_id": tool_call_id, "result": error_msg, "name": tool_name})
                
            except HTTPException as e:
                await LegacyLogManager.log_failure(user_api_key_auth, logging_request_data, e)
                log.error(f"HTTPException in MCP tool call: {str(e)}")
                error_msg = f"Tool call failed: {str(e.detail) if hasattr(e, 'detail') else str(e)}"
                tool_results.append({"tool_call_id": tool_call_id, "result": error_msg, "name": tool_name})
                
            except Exception as e:
                await LegacyLogManager.log_failure(user_api_key_auth, logging_request_data, e)
                log.exception(f"Error executing MCP tool call: {e}")
                tool_results.append({"tool_call_id": tool_call_id, "result": f"Error executing tool: {str(e)}", "name": tool_name})

        return tool_results

    @staticmethod
    async def _make_follow_up_call(
        follow_up_input: List[Any],
        model: str,
        all_tools: Optional[List[Any]],
        response_id: str,
        **call_params: Any,
    ) -> Union[ResponsesAPIResponse, BaseResponsesAPIStreamingIterator]:
        from anchor.action.api.aresponse import aresponses
        return await aresponses(
            input=follow_up_input,
            model=model,
            tools=all_tools,  
            previous_response_id=response_id,  
            **call_params,
        )

    @staticmethod
    def _create_mcp_streaming_response(
        input: Union[str, Any],
        model: str,
        all_tools: Optional[List[Any]],
        mcp_tools_with_litellm_proxy: List[Any],
        mcp_discovery_events: List[Any],
        call_params: Dict[str, Any],
        previous_response_id: Optional[str],
        tool_server_map: dict[str, str],
        **kwargs,
    ) -> Any:
        request_params = MCPPayloadUtils._build_request_params(
            input=input,
            model=model,
            all_tools=all_tools,
            call_params=call_params,
            previous_response_id=previous_response_id,
            **kwargs,
        )

        from anchor.surface.legacy.mcp.stream import MCPEnhancedStreamingIterator
        return MCPEnhancedStreamingIterator(
            base_iterator=None,  
            mcp_events=mcp_discovery_events,  
            tool_server_map=tool_server_map,
            mcp_tools_with_litellm_proxy=mcp_tools_with_litellm_proxy,
            user_api_key_auth=kwargs.get("user_api_key_auth") or kwargs.get("litellm_metadata", {}).get("user_api_key_auth"),
            original_request_params=request_params,
        )