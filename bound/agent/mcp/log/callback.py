# bound.agent.mcp.log.callback
## @lineage: xphi.agent.mcp.log.callback
from anchor.surface.mcps.types import LoggingMessageNotificationParams
from arch.proto.event.next import LogEvent
from watcher.plane.emitter import get_emitter

from bound.agent.mcp.client import MCPClient

emitter = get_emitter(__name__)

async def mcp_log_callback(params: LoggingMessageNotificationParams) -> None:
    """
    MCP 서버에서 전송되는 로그를 내부 LogEvent 규격으로 변환하여 Emitter에 발행합니다.
    발행된 이벤트는 등록된 interceptor(예: otel_log_interceptor)를 통해 자동으로 수집 및 트레이싱
    """
    ## MCP 로그 레벨을 내부 시스템 규격(대문자)으로 정규화
    level_map = {
        "error": "ERROR",
        "warning": "WARNING",
        "debug": "DEBUG",
        "info": "INFO"
    }
    normalized_level = level_map.get(str(params.level).lower(), "INFO")
    source_name = params.logger if params.logger else "unknown-module"

    ## 규격화된 LogEvent 객체 생성
    event = LogEvent(
        level=normalized_level,
        message=params.data,
        source_id=f"mcp-server::{source_name}",
        context={
            "phase": "mcp_execution",
            "mcp_logger": params.logger,
            "mcp_level": params.level
        }
    )
    emitter.emit(event)

def create_mcp_client_with_logs(config) -> MCPClient:
    return MCPClient(
        config=config, 
        logging_callback=mcp_log_callback
    )