# bound.adapter.legacy.proxy.reverse
## @lineage: anchor.surface.legacy.proxy.reverse
from typing import Any, Dict, List, Optional, Protocol, Tuple
from pydantic import BaseModel, ConfigDict

from watcher.plane.emitter import get_emitter

log = get_emitter("proxy.reverse")

class BraneAuthContext(BaseModel):
    """기존 LiteLLM의 user_api_key_auth 및 ObjectPermissionTable을 대체하는 Brane 시스템 전용 순수 인증 객체"""
    model_config = ConfigDict(frozen=True)
    user_id: str
    is_admin: bool = False
    
    ## 정적 권한 (RBAC) - 이 사용자가 접근 가능한 개별 서버 및 툴셋(그룹)
    allowed_mcp_servers: List[str] = []
    allowed_toolsets: List[str] = []

class ToolsetDefinition(BaseModel):
    """툴셋(도구 모음) 메타데이터"""
    id: str
    name: str

class ToolRegistryProtocol(Protocol):
    """MCP 서버와 툴셋의 메타데이터 및 실제 도구를 제공하는 인터페이스."""
    async def get_server_by_name(self, name: str) -> Optional[Any]:
        """이름으로 단일 MCP 서버의 존재 여부 및 메타데이터를 반환"""
        ...
        
    async def get_toolset_by_name(self, name: str) -> Optional[ToolsetDefinition]:
        """이름으로 툴셋 그룹을 반환"""
        ...
        
    async def get_servers_for_toolset(self, toolset_id: str) -> List[str]:
        """특정 툴셋에 속한 MCP 서버들의 이름(id) 목록을 반환"""
        ...
        
    async def fetch_tools_from_servers(self, server_names: List[str]) -> List[Any]:
        """(Low-level Server 클라이언트를 통해) 실제 가용한 도구 목록을 반환"""
        ...

class BraneToolCatalogManager:
    """LLM에게 도구를 노출하기 전, 정적 권한(RBAC)을 검증하고 필터링하는 매니저"""
    
    def __init__(self, registry: ToolRegistryProtocol):
        self.registry = registry

    async def get_authorized_tools(
        self,
        auth_context: BraneAuthContext,
        requested_names: List[str]
    ) -> Tuple[List[Any], List[str]]:
        """요청받은 서버/툴셋 이름 목록을 분석하여, 사용자 권한에 맞는 실제 서버 이름 목록을 도출하고, 그에 해당하는 도구 리스트를 반환"""
        if not auth_context:
            log.warning("No auth_context provided. Returning empty tools.")
            return [], []

        resolved_server_names: set[str] = set()

        ## 요청된 이름들을 순회하며 Server와 Toolset을 분류 및 권한 검증
        for name in requested_names:
            ## (A) 툴셋인지 먼저 확인
            toolset = await self.registry.get_toolset_by_name(name)
            if toolset:
                if auth_context.is_admin or toolset.id in auth_context.allowed_toolsets:
                    ## 툴셋에 접근 권한이 있다면, 해당 툴셋 안의 서버들을 모두 추가
                    servers_in_toolset = await self.registry.get_servers_for_toolset(toolset.id)
                    resolved_server_names.update(servers_in_toolset)
                else:
                    log.debug(f"User '{auth_context.user_id}' lacks access to toolset '{name}'. Skipping.")
                continue

            ## (B) 툴셋이 아니라면 단일 서버인지 확인
            server = await self.registry.get_server_by_name(name)
            if server:
                if auth_context.is_admin or name in auth_context.allowed_mcp_servers:
                    resolved_server_names.add(name)
                else:
                    log.debug(f"User '{auth_context.user_id}' lacks access to MCP server '{name}'. Skipping.")
                continue

            ## 둘 다 아닌 경우
            log.warning(f"Could not resolve '{name}' as either a toolset or an MCP server.")

        ## 최종 승인된 서버가 없으면 빠른 반환 (Fail-fast)
        effective_server_names = list(resolved_server_names)
        if not effective_server_names:
            return [], []

        ## 레지스트리를 통해 실제 도구(Tool) 명세서 페칭
        try:
            tools = await self.registry.fetch_tools_from_servers(effective_server_names)
        except Exception as e:
            log.error(f"Failed to fetch tools from registry: {e}")
            tools = []
        return tools, effective_server_names