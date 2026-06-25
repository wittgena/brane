# bound.adapter.legacy.engine
## @lineage: bound.adapter.legacy.mcp.engine
## @lineage: anchor.surface.legacy.mcp.engine
from bound.adapter.legacy.mcp.payload import MCPPayloadUtils
from bound.adapter.legacy.interface import MCPAuthManager, MCPRouteManager, MCPLogManager
from typing import List, Dict, Any

class MCPEngine:
    """
    상태를 가지지 않으며, 주입받은 매니저들을 오케스트레이션만 하는 순수 엔진
    """
    def __init__(
        self, 
        auth_manager: MCPAuthManager, 
        route_manager: MCPRouteManager, 
        log_manager: MCPLogManager
    ):
        self.auth = auth_manager
        self.route = route_manager
        self.log = log_manager

    async def execute_tools(self, api_key: str, tool_calls: List[Any]) -> List[Dict[str, Any]]:
        tool_results = []
        
        for tool_call in tool_calls:
            # 1. Payload 파싱 (순수 함수)
            tool_name, arguments, call_id = MCPPayloadUtils.extract_details(tool_call)
            
            # 2. 로깅 시작
            trace_id = await self.log.log_pre_call({"tool": tool_name, "args": arguments})
            
            try:
                # 3. 권한 검증
                if not await self.auth.verify_tool_access(api_key, tool_name):
                    raise PermissionError(f"Access denied to {tool_name}")

                # 4. 실제 실행 (어떤 엔진이 도는지 엔진은 모름)
                server_name = MCPPayloadUtils.extract_server_name(tool_name)
                result = await self.route.execute_tool(server_name, tool_name, arguments)
                
                # 5. 성공 처리
                await self.log.log_success(trace_id, result)
                parsed_result = MCPPayloadUtils.parse_result(result)
                
                tool_results.append({"tool_call_id": call_id, "result": parsed_result})
                
            except Exception as e:
                # 6. 실패 처리
                await self.log.log_failure(trace_id, e)
                tool_results.append({"tool_call_id": call_id, "result": f"Error: {str(e)}"})
                
        return tool_results