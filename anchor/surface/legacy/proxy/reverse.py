# anchor.surface.legacy.proxy.reverse
## @lineage: bound.adapter.litellm.proxy.reverse
## @lineage: bound.legacy.proxy.reverse
## @lineage: bound.server.proxy.reverse
## @lineage: bound.proxy.reverse
## @lineage: bound.client.mcp.reverse
from typing import Any, Iterable, List, Optional, Tuple, Dict
from litellm.proxy._types import LiteLLM_ObjectPermissionTable
from litellm.proxy._experimental.mcp_server.mcp_server_manager import global_mcp_server_manager
from litellm.proxy._experimental.mcp_server.server import (
    _get_allowed_mcp_servers_from_mcp_server_names,
    _get_tools_from_mcp_servers,
)
from litellm.proxy.management_endpoints.common_utils import _user_has_admin_view
from watcher.plane.emitter import get_emitter

log = get_emitter("proxy.reverse")

class LegacyLitellmToolsManager:
    """
    litellm의 복잡한 도구 조회 및 권한 필터링 로직을 캡슐화한 어댑터.
    이 클래스가 MCPProxyHandler에서 _get_mcp_tools_from_manager 역할을 대체합니다.
    """

    @staticmethod
    async def apply_toolset_permissions(
        resolved_toolset_ids: List[str],
        resolved_mcp_servers: List[str],
        user_api_key_auth: Any,
    ) -> Any:
        # 기존 MCPProxyHandler._apply_toolset_permissions 코드를 그대로 가져옵니다.
        try:
            tool_permissions = await global_mcp_server_manager.resolve_toolset_tool_permissions(
                toolset_ids=resolved_toolset_ids
            )
            all_server_ids = list(set(tool_permissions.keys()) | set(resolved_mcp_servers))
            existing_op = getattr(user_api_key_auth, "object_permission", None)
            
            if existing_op is not None:
                merged_tool_perms = dict(existing_op.mcp_tool_permissions or {})
                for server_id, tool_names in tool_permissions.items():
                    existing_tools = merged_tool_perms.get(server_id, [])
                    merged_tool_perms[server_id] = list(set(existing_tools) | set(tool_names))
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
            return user_api_key_auth.model_copy(update={"object_permission": updated_op})
        except Exception as _e:
            log.debug(f"Could not apply toolset permissions: {_e}")
            return user_api_key_auth

    @staticmethod
    async def get_tools_from_manager(
        user_api_key_auth: Any,
        mcp_servers: List[str], # 이미 파싱된 서버 이름 리스트를 받습니다.
        litellm_trace_id: Optional[str] = None,
        mcp_auth_header: Optional[str] = None,
        mcp_server_auth_headers: Optional[Dict[str, Dict[str, str]]] = None,
    ) -> Tuple[List[Any], List[str]]:
        # 기존 _get_mcp_tools_from_manager의 핵심 로직 (DB 조회 등)
        resolved_mcp_servers: List[str] = []
        resolved_toolset_ids: List[str] = []
        
        for name in mcp_servers:
            if not global_mcp_server_manager.get_mcp_server_by_name(name):
                # 파일 상단에 두지 않고 지연 임포트했던 prisma_client는 
                # 어댑터 내부에서만 안전하게 캡슐화합니다.
                from litellm.proxy.proxy_server import prisma_client 
                try:
                    if prisma_client is not None:
                        toolset = await global_mcp_server_manager.get_toolset_by_name_cached(prisma_client, name)
                        if toolset is not None:
                            if user_api_key_auth is not None:
                                is_admin = _user_has_admin_view(user_api_key_auth)
                                if not is_admin:
                                    op = getattr(user_api_key_auth, "object_permission", None)
                                    granted = getattr(op, "mcp_toolsets", None) if op else None
                                    if granted is None or toolset.toolset_id not in granted:
                                        log.debug(f"Key does not have access to toolset '{name}', skipping.")
                                        continue
                            resolved_toolset_ids.append(toolset.toolset_id)
                            continue
                except Exception as _e:
                    log.debug(f"Could not resolve '{name}' as toolset: {_e}")
            resolved_mcp_servers.append(name)

        if resolved_toolset_ids and user_api_key_auth is not None:
            user_api_key_auth = await LegacyLitellmToolsManager.apply_toolset_permissions(
                resolved_toolset_ids=resolved_toolset_ids,
                resolved_mcp_servers=resolved_mcp_servers,
                user_api_key_auth=user_api_key_auth,
            )

        effective_server_filter = None if resolved_toolset_ids else (resolved_mcp_servers or None)

        tools = await _get_tools_from_mcp_servers(
            user_api_key_auth=user_api_key_auth,
            mcp_auth_header=mcp_auth_header,
            mcp_servers=effective_server_filter,
            mcp_server_auth_headers=mcp_server_auth_headers,
            log_list_tools_to_spendlogs=True,
            list_tools_log_source="responses",
            litellm_trace_id=litellm_trace_id,
        )

        allowed_mcp_server_ids = await global_mcp_server_manager.get_allowed_mcp_servers(user_api_key_auth)
        allowed_mcp_servers_objs = global_mcp_server_manager.get_mcp_servers_from_ids(allowed_mcp_server_ids)

        allowed_mcp_servers_filtered = await _get_allowed_mcp_servers_from_mcp_server_names(
            mcp_servers=effective_server_filter,
            allowed_mcp_servers=allowed_mcp_servers_objs,
        )

        server_names: List[str] = []
        for server in allowed_mcp_servers_filtered:
            if server is None: continue
            server_name = getattr(server, "server_name", None) or getattr(server, "alias", None) or getattr(server, "name", None)
            if isinstance(server_name, str):
                server_names.append(server_name)

        return tools, server_names
