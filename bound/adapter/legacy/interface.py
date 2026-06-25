# bound.adapter.legacy.interface
from typing import Protocol, List, Dict, Any, Optional

class MCPAuthManager(Protocol):
    """권한 검증을 담당하는 인터페이스"""
    async def get_allowed_server_names(self, api_key: str, requested_servers: Optional[List[str]]) -> List[str]:
        ...
    
    async def verify_tool_access(self, api_key: str, tool_name: str) -> bool:
        ...

class MCPRouteManager(Protocol):
    """실제 MCP 서버와의 통신 및 툴 실행을 담당하는 인터페이스"""
    async def fetch_tools(self, allowed_servers: List[str]) -> List[Dict[str, Any]]:
        ...
        
    async def execute_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any]) -> Any:
        ...

class MCPLogManager(Protocol):
    """과금, 추적, 에러 로깅을 담당하는 인터페이스"""
    async def log_pre_call(self, request_data: Dict[str, Any]) -> str:
        """호출 전 기록을 남기고 trace_id를 반환"""
        ...
        
    async def log_success(self, trace_id: str, result: Any) -> None:
        ...
        
    async def log_failure(self, trace_id: str, error: Exception) -> None:
        ...