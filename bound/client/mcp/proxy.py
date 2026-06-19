# bound.client.mcp.proxy
## @lineage: bound.handler.support.mcp.proxy
import re
import traceback
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

from litellm.proxy._experimental.mcp_server.utils import split_server_prefix_from_name
from litellm.proxy._types import LiteLLM_ObjectPermissionTable
from litellm.proxy._experimental.mcp_server.mcp_server_manager import global_mcp_server_manager
from litellm.proxy._experimental.mcp_server.server import (
    _get_allowed_mcp_servers_from_mcp_server_names,
    _get_tools_from_mcp_servers,
)
from litellm.proxy.management_endpoints.common_utils import _user_has_admin_view
from litellm.experimental_mcp_client.tools import (
    transform_mcp_tool_to_openai_responses_api_tool,
    transform_mcp_tool_to_openai_tool,
)
from litellm.exceptions import BlockedPiiEntityError, GuardrailRaisedException
from litellm.proxy._experimental.mcp_server.mcp_server_manager import global_mcp_server_manager

from anchor.config.constants import MAXIMUM_TRACEBACK_LINES_TO_LOG
from anchor.switch.params import ResponsesAPIResponse

from bound.xor.scope.plane.delegator import Logging as LiteLLMLoggingObj
from bound.client.handler.stream.iterator import BaseResponsesAPIStreamingIterator
from anchor.router.model.types.utils import CallTypes, Choices, StandardLoggingMCPToolCall
from bound.client.wrapper import function_setup
from bound.client.mcp.payload import MCPPayloadUtils
from xphi.manager.rule.validator import Rules

if TYPE_CHECKING:
    from mcp.types import Tool as MCPTool
    from litellm.proxy.utils import ProxyLogging
else:
    MCPTool = Any

from arch.proto.phase.gate import uuid
from watcher.plane.emitter import get_emitter

log = get_emitter("proxy.mcp")

ToolParam = Any
LITELLM_PROXY_MCP_SERVER_URL = "litellm_proxy"
LITELLM_PROXY_MCP_SERVER_URL_PREFIX = f"{LITELLM_PROXY_MCP_SERVER_URL}/mcp/"
_PROXY_MCP_PATH_RE = re.compile(r"^https?://.+/mcp/([^/]+)$")

class MCPProxyHandler:
    @staticmethod
    def _create_tool_execution_events(
        tool_calls: List[Any], tool_results: List[Dict[str, Any]]
    ) -> List[Any]:
        tool_execution_events: List[Any] = []

        # Create events for each tool execution
        for tool_result in tool_results:
            tool_call_id = tool_result.get("tool_call_id", "unknown")
            result_text = tool_result.get("result", "")

            # Extract tool name and arguments from tool calls
            tool_name = "unknown"
            tool_arguments = "{}"
            for tool_call in tool_calls:
                (
                    name,
                    args,
                    call_id,
                ) = LiteLLM_Proxy_MCP_Handler._extract_tool_call_details(tool_call)
                if call_id == tool_call_id:
                    tool_name = name or "unknown"
                    tool_arguments = args or "{}"
                    break

            from bound.client.mcp.stream import create_mcp_call_events
            execution_events = create_mcp_call_events(
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                arguments=tool_arguments,  # Use actual arguments
                result=result_text,
                base_item_id=f"mcp_{uuid.uuid4().hex[:8]}",  # Unique ID for each tool call
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
                    if isinstance(server_url, str) and server_url.startswith(
                        LITELLM_PROXY_MCP_SERVER_URL
                    ):
                        return True
                    if isinstance(server_url, str) and _PROXY_MCP_PATH_RE.match(
                        server_url
                    ):
                        return True
        return False

    @staticmethod
    async def _apply_toolset_permissions(
        resolved_toolset_ids: List[str],
        resolved_mcp_servers: List[str],
        user_api_key_auth: Any,
    ) -> Any:
        try:
            tool_permissions = (
                await global_mcp_server_manager.resolve_toolset_tool_permissions(
                    toolset_ids=resolved_toolset_ids
                )
            )
            all_server_ids = list(
                set(tool_permissions.keys()) | set(resolved_mcp_servers)
            )
            existing_op = user_api_key_auth.object_permission
            if existing_op is not None:
                merged_tool_perms = dict(existing_op.mcp_tool_permissions or {})
                for server_id, tool_names in tool_permissions.items():
                    existing_tools = merged_tool_perms.get(server_id, [])
                    merged_tool_perms[server_id] = list(
                        set(existing_tools) | set(tool_names)
                    )
                updated_op = existing_op.model_copy(
                    update={
                        "mcp_servers": all_server_ids,
                        "mcp_tool_permissions": merged_tool_perms,
                        "mcp_toolsets": [],
                    }
                )
            else:
                updated_op = LiteLLM_ObjectPermissionTable(
                    object_permission_id="toolset-scope",
                    mcp_servers=all_server_ids,
                    mcp_tool_permissions=tool_permissions,
                )
            return user_api_key_auth.model_copy(
                update={"object_permission": updated_op}
            )
        except Exception as _e:
            log.debug(f"Could not apply toolset permissions: {_e}")
            return user_api_key_auth

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
                # if user specifies servers as server_url: litellm_proxy/mcp/zapier,github then return zapier,github
                server_url = (
                    _tool.get("server_url", "") if isinstance(_tool, dict) else ""
                )
                if isinstance(server_url, str) and server_url.startswith(
                    LITELLM_PROXY_MCP_SERVER_URL_PREFIX
                ):
                    mcp_servers.append(server_url.split("/")[-1])

        resolved_mcp_servers: List[str] = []
        resolved_toolset_ids: List[str] = []
        for name in mcp_servers:
            if not global_mcp_server_manager.get_mcp_server_by_name(name):
                from litellm.proxy.proxy_server import prisma_client
                try:
                    if prisma_client is not None:
                        toolset = await global_mcp_server_manager.get_toolset_by_name_cached(prisma_client, name)
                        if toolset is not None:
                            # Access control: only allow if the key explicitly grants this toolset.
                            if user_api_key_auth is not None:
                                is_admin = _user_has_admin_view(user_api_key_auth)
                                if not is_admin:
                                    op = user_api_key_auth.object_permission
                                    granted = (
                                        getattr(op, "mcp_toolsets", None)
                                        if op
                                        else None
                                    )
                                    # None means no grants configured → deny (consistent with
                                    # fetch_mcp_toolsets which returns [] for unconfigured keys)
                                    if (
                                        granted is None
                                        or toolset.toolset_id not in granted
                                    ):
                                        log.debug(
                                            f"Key does not have access to toolset '{name}', skipping."
                                        )
                                        continue
                            resolved_toolset_ids.append(toolset.toolset_id)
                            # Don't add to resolved_mcp_servers — toolset scope
                            # restricts via object_permission, not server name filter.
                            continue
                except Exception as _e:
                    log.debug(f"Could not resolve '{name}' as toolset: {_e}")
            resolved_mcp_servers.append(name)

        # Apply all resolved toolsets at once (union), avoiding permission overwrite.
        if resolved_toolset_ids and user_api_key_auth is not None:
            user_api_key_auth = (
                await MCPProxyHandler._apply_toolset_permissions(
                    resolved_toolset_ids=resolved_toolset_ids,
                    resolved_mcp_servers=resolved_mcp_servers,
                    user_api_key_auth=user_api_key_auth,
                )
            )

        effective_server_filter = (
            None if resolved_toolset_ids else (resolved_mcp_servers or None)
        )

        tools = await _get_tools_from_mcp_servers(
            user_api_key_auth=user_api_key_auth,
            mcp_auth_header=mcp_auth_header,
            mcp_servers=effective_server_filter,
            mcp_server_auth_headers=mcp_server_auth_headers,
            log_list_tools_to_spendlogs=True,
            list_tools_log_source="responses",
            litellm_trace_id=litellm_trace_id,
        )

        allowed_mcp_server_ids = (
            await global_mcp_server_manager.get_allowed_mcp_servers(user_api_key_auth)
        )
        allowed_mcp_servers = global_mcp_server_manager.get_mcp_servers_from_ids(  # type: ignore[attr-defined]
            allowed_mcp_server_ids
        )

        allowed_mcp_servers = await _get_allowed_mcp_servers_from_mcp_server_names(
            mcp_servers=effective_server_filter,
            allowed_mcp_servers=allowed_mcp_servers,
        )

        server_names: List[str] = []
        for server in allowed_mcp_servers:
            if server is None:
                continue
            server_name = (
                getattr(server, "server_name", None)
                or getattr(server, "alias", None)
                or getattr(server, "name", None)
            )
            if isinstance(server_name, str):
                server_names.append(server_name)

        return tools, server_names

    @staticmethod
    def _deduplicate_mcp_tools(
        mcp_tools: List[MCPTool], allowed_mcp_servers: List[str]
    ) -> tuple[List[MCPTool], dict[str, str]]:
        seen_names = set()
        deduplicated_tools = []
        tool_server_map: dict[str, str] = {}

        for tool in mcp_tools:
            if isinstance(tool, dict):
                tool_name = tool.get("name")
            else:
                tool_name = getattr(tool, "name", None)

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
        """Filter MCP tools based on allowed_tools parameter from the original tool configs."""
        # Collect all allowed tool names from all MCP tool configs
        allowed_tool_names = set()
        for tool_config in mcp_tools_with_litellm_proxy:
            if isinstance(tool_config, dict) and "allowed_tools" in tool_config:
                allowed_tools = tool_config.get("allowed_tools", [])
                if isinstance(allowed_tools, list):
                    allowed_tool_names.update(allowed_tools)

        # If no allowed_tools specified, return all tools
        if not allowed_tool_names:
            return mcp_tools

        # Filter tools based on allowed names
        filtered_tools = []
        for mcp_tool in mcp_tools:
            if isinstance(mcp_tool, dict):
                tool_name = mcp_tool.get("name")
            else:
                tool_name = getattr(mcp_tool, "name", None)

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
        ) = await MCPProxyHandler._process_mcp_tools_without_openai_transform(
            user_api_key_auth,
            mcp_tools_with_litellm_proxy,
            litellm_trace_id=litellm_trace_id,
        )

        openai_tools = MCPProxyHandler._transform_mcp_tools_to_openai(
            deduplicated_mcp_tools
        )

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

        # Step 1: Fetch MCP tools from manager
        (
            mcp_tools_fetched,
            allowed_mcp_servers,
        ) = await MCPProxyHandler._get_mcp_tools_from_manager(
            user_api_key_auth=user_api_key_auth,
            mcp_tools_with_litellm_proxy=mcp_tools_with_litellm_proxy,
            litellm_trace_id=litellm_trace_id,
            mcp_auth_header=mcp_auth_header,
            mcp_server_auth_headers=mcp_server_auth_headers,
        )

        # Step 2: Filter tools based on allowed_tools parameter
        filtered_mcp_tools = (
            MCPProxyHandler._filter_mcp_tools_by_allowed_tools(
                mcp_tools=mcp_tools_fetched,
                mcp_tools_with_litellm_proxy=mcp_tools_with_litellm_proxy,
            )
        )

        # Step 3: Deduplicate tools after filtering
        (
            deduplicated_mcp_tools,
            tool_server_map,
        ) = MCPProxyHandler._deduplicate_mcp_tools(
            filtered_mcp_tools, allowed_mcp_servers
        )

        return deduplicated_mcp_tools, tool_server_map

    @staticmethod
    def _transform_mcp_tools_to_openai(
        mcp_tools: List[Any],
        target_format: Literal["responses", "chat"] = "responses",
    ) -> List[Any]:
        """Transform MCP tools to OpenAI-compatible format."""
        openai_tools: List[Any] = []
        for mcp_tool in mcp_tools:
            openai_tool: Any
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
        """Check if we should auto-execute tool calls.

        Only auto-execute tools if user passed a MCP tool with require_approval set to "never".


        """
        for tool in mcp_tools_with_litellm_proxy:
            if isinstance(tool, dict):
                if tool.get("require_approval") == "never":
                    return True
            elif getattr(tool, "require_approval", None) == "never":
                return True
        return False

    @staticmethod
    async def _execute_tool_calls(  # noqa: PLR0915
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
        from litellm.proxy.proxy_server import proxy_logging_obj

        tool_results = []
        tool_call_id: Optional[str] = None
        rules_obj = Rules()
        for tool_call in tool_calls:
            logging_request_data: Dict[str, Any] = {}
            tool_name: Optional[str] = None
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

                # Remove the server name prefix if the tool name includes it.
                sanitized_tool_name = tool_name
                unprefixed_name, prefixed_server_name = split_server_prefix_from_name(
                    tool_name
                )
                if (
                    prefixed_server_name
                    and prefixed_server_name == server_name
                    and unprefixed_name
                ):
                    sanitized_tool_name = unprefixed_name

                start_time = datetime.now()
                logging_input = [
                    {
                        "role": "tool",
                        "content": {
                            "tool_name": sanitized_tool_name,
                            "arguments": parsed_arguments,
                        },
                    }
                ]
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
                    # Add proxy_server_request with arguments for callback logging
                    "proxy_server_request": {
                        "url": "/mcp/tools/call",
                        "method": "POST",
                        "headers": {},
                        "body": {
                            "name": sanitized_tool_name,
                            "arguments": parsed_arguments,
                        },
                    },
                }
                if litellm_trace_id:
                    logging_request_data["litellm_trace_id"] = litellm_trace_id
                user_identifier = None
                if user_api_key_auth is not None:
                    user_api_key = getattr(user_api_key_auth, "api_key", None)
                    if user_api_key:
                        logging_request_data["metadata"]["user_api_key"] = user_api_key

                    user_identifier = getattr(
                        user_api_key_auth, "end_user_id", None
                    ) or getattr(user_api_key_auth, "user_id", None)
                if user_identifier:
                    logging_request_data["user"] = user_identifier

                litellm_logging_obj: Optional[LiteLLMLoggingObj] = None
                try:
                    litellm_logging_obj, _ = function_setup(
                        original_function="call_mcp_tool",
                        rules_obj=rules_obj,
                        start_time=start_time,
                        **logging_request_data,
                    )
                except Exception as logging_error:
                    log.debug(
                        "Failed to initialize logging for MCP tool call %s: %s",
                        tool_name,
                        logging_error,
                    )
                    litellm_logging_obj = None

                logging_request_data["litellm_logging_obj"] = litellm_logging_obj
                logging_request_data["arguments"] = parsed_arguments

                if litellm_logging_obj:
                    try:
                        litellm_logging_obj.pre_call(
                            input=logging_input,
                            api_key="",
                        )
                    except Exception:
                        log.exception(
                            "Failed to run pre_call for MCP tool logging"
                        )

                standard_logging_mcp_tool_call: StandardLoggingMCPToolCall = {
                    "name": sanitized_tool_name,
                    "arguments": parsed_arguments,
                    "namespaced_tool_name": tool_name,
                }
                mcp_server = global_mcp_server_manager._get_mcp_server_from_tool_name(
                    tool_name
                )
                if mcp_server:
                    mcp_info = mcp_server.mcp_info or {}
                    standard_logging_mcp_tool_call["mcp_server_name"] = (
                        mcp_info.get("server_name")
                        or getattr(mcp_server, "server_name", None)
                        or server_name
                    )
                    logo_url = mcp_info.get("logo_url")
                    if logo_url:
                        standard_logging_mcp_tool_call["mcp_server_logo_url"] = logo_url
                    cost_info = mcp_info.get("mcp_server_cost_info")
                    if cost_info:
                        standard_logging_mcp_tool_call["mcp_server_cost_info"] = (
                            cost_info
                        )

                if litellm_logging_obj:
                    litellm_logging_obj.model_call_details["mcp_tool_call_metadata"] = (
                        standard_logging_mcp_tool_call
                    )
                    litellm_logging_obj.model = f"MCP: {tool_name}"
                    litellm_logging_obj.call_type = CallTypes.call_mcp_tool.value

                result = await global_mcp_server_manager.call_tool(
                    server_name=server_name,
                    name=sanitized_tool_name,
                    arguments=parsed_arguments,
                    user_api_key_auth=user_api_key_auth,
                    mcp_auth_header=mcp_auth_header,
                    mcp_server_auth_headers=mcp_server_auth_headers,
                    oauth2_headers=oauth2_headers,
                    raw_headers=raw_headers,
                    proxy_logging_obj=proxy_logging_obj,
                )

                if litellm_logging_obj:
                    try:
                        litellm_logging_obj.post_call(original_response=result)
                        end_time = datetime.now()
                        await litellm_logging_obj.async_post_mcp_tool_call_hook(
                            kwargs=litellm_logging_obj.model_call_details,
                            response_obj=result,
                            start_time=start_time,
                            end_time=end_time,
                        )
                        await litellm_logging_obj.async_success_handler(
                            result=result,
                            start_time=start_time,
                            end_time=end_time,
                        )
                    except Exception:
                        log.exception(
                            "Failed to log MCP tool call success for %s", tool_name
                        )

                # Format result for inclusion in response
                result_text = MCPPayloadUtils._parse_mcp_result(result)
                tool_results.append(
                    {
                        "tool_call_id": tool_call_id,
                        "result": result_text,
                        "name": tool_name,
                    }
                )

            except BlockedPiiEntityError as e:
                await MCPProxyHandler._log_mcp_tool_failure(
                    proxy_logging_obj=proxy_logging_obj,
                    user_api_key_auth=user_api_key_auth,
                    request_data=logging_request_data,
                    error=e,
                )
                log.error(
                    f"BlockedPiiEntityError in MCP tool call: {str(e)}"
                )
                error_message = f"Tool call blocked: PII entity '{getattr(e, 'entity_type', 'unknown')}' detected by guardrail '{getattr(e, 'guardrail_name', 'unknown')}'. {str(e)}"
                tool_results.append(
                    {
                        "tool_call_id": tool_call_id,
                        "result": error_message,
                        "name": tool_name,
                    }
                )
            except GuardrailRaisedException as e:
                await MCPProxyHandler._log_mcp_tool_failure(
                    proxy_logging_obj=proxy_logging_obj,
                    user_api_key_auth=user_api_key_auth,
                    request_data=logging_request_data,
                    error=e,
                )
                log.error(
                    f"GuardrailRaisedException in MCP tool call: {str(e)}"
                )
                error_message = f"Tool call blocked: Guardrail '{getattr(e, 'guardrail_name', 'unknown')}' violation. {str(e)}"
                tool_results.append(
                    {
                        "tool_call_id": tool_call_id,
                        "result": error_message,
                        "name": tool_name,
                    }
                )
            except HTTPException as e:
                await MCPProxyHandler._log_mcp_tool_failure(
                    proxy_logging_obj=proxy_logging_obj,
                    user_api_key_auth=user_api_key_auth,
                    request_data=logging_request_data,
                    error=e,
                )
                log.error(f"HTTPException in MCP tool call: {str(e)}")
                error_message = f"Tool call failed: {str(e.detail) if hasattr(e, 'detail') else str(e)}"
                tool_results.append(
                    {
                        "tool_call_id": tool_call_id,
                        "result": error_message,
                        "name": tool_name,
                    }
                )
            except Exception as e:
                await MCPProxyHandler._log_mcp_tool_failure(
                    proxy_logging_obj=proxy_logging_obj,
                    user_api_key_auth=user_api_key_auth,
                    request_data=logging_request_data,
                    error=e,
                )
                log.exception(f"Error executing MCP tool call: {e}")
                tool_results.append(
                    {
                        "tool_call_id": tool_call_id,
                        "result": f"Error executing tool: {str(e)}",
                        "name": tool_name,
                    }
                )

        return tool_results

    @staticmethod
    async def _make_follow_up_call(
        follow_up_input: List[Any],
        model: str,
        all_tools: Optional[List[Any]],
        response_id: str,
        **call_params: Any,
    ) -> Union[ResponsesAPIResponse, BaseResponsesAPIStreamingIterator]:
        from bound.client.aresponse import aresponses
        """Make follow-up response API call with tool results."""
        return await aresponses(
            input=follow_up_input,
            model=model,
            tools=all_tools,  # Keep tools for potential future calls
            previous_response_id=response_id,  # Link to previous response
            **call_params,
        )

    @staticmethod
    async def _log_mcp_tool_failure(
        *,
        proxy_logging_obj: Optional["ProxyLogging"],
        user_api_key_auth: Any,
        request_data: Dict[str, Any],
        error: Exception,
    ) -> None:
        """Log MCP tool failures via proxy logging hooks."""

        if proxy_logging_obj is None or user_api_key_auth is None:
            return

        try:
            traceback_str = traceback.format_exc(limit=MAXIMUM_TRACEBACK_LINES_TO_LOG)
            await proxy_logging_obj.post_call_failure_hook(
                request_data=request_data,
                original_exception=error,
                user_api_key_dict=user_api_key_auth,
                route="/responses/mcp/call_tool",
                traceback_str=traceback_str,
            )
        except Exception:
            log.exception("Failed to log MCP tool call failure")

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
        """
        Create MCP enhanced streaming response that handles the full MCP workflow.

        This creates a streaming iterator that:
        1. Immediately emits MCP discovery events
        2. Makes the LLM call and streams the response
        3. Handles tool execution and follow-up calls
        """
        # Build the complete request parameters by merging all sources
        request_params = MCPPayloadUtils._build_request_params(
            input=input,
            model=model,
            all_tools=all_tools,
            call_params=call_params,
            previous_response_id=previous_response_id,
            **kwargs,
        )

        from bound.client.mcp.stream import MCPEnhancedStreamingIterator
        return MCPEnhancedStreamingIterator(
            base_iterator=None,  # Will be created internally
            mcp_events=mcp_discovery_events,  # Pre-generated MCP discovery events
            tool_server_map=tool_server_map,
            mcp_tools_with_litellm_proxy=mcp_tools_with_litellm_proxy,
            user_api_key_auth=kwargs.get("user_api_key_auth")
            or kwargs.get("litellm_metadata", {}).get("user_api_key_auth"),
            original_request_params=request_params,
        )