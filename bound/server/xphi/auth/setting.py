# bound.server.xphi.auth.setting
## @lineage: xphi.server.auth.setting
## @lineage: bound.server.auth.setting
## @lineage: bound.server.mcps.auth.setting
## @lineage: anchor.mcp.server.auth.setting
## @lineage: anchor.mcp.server.auth.settgins
import datetime
from pydantic import AnyHttpUrl, BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict
from bound.server.xphi.auth.provider import SimpleAuthSettings

# --- 1. 공통 설정 모델 ---
class AuthServerSettings(BaseModel):
    """Authorization Server(브로커)를 위한 설정"""
    host: str = "localhost"
    port: int = 9000
    server_url: AnyHttpUrl = AnyHttpUrl("http://localhost:9000")
    auth_callback_path: str = "http://localhost:9000/login/callback"

class ResourceServerSettings(BaseSettings):
    """Resource Server(MCP 도구)를 위한 설정"""
    model_config = SettingsConfigDict(env_prefix="MCP_RESOURCE_")
    host: str = "localhost"
    port: int = 8001
    server_url: AnyHttpUrl = AnyHttpUrl("http://localhost:8001/mcp")
    auth_server_url: AnyHttpUrl = AnyHttpUrl("http://localhost:9000")
    auth_server_introspection_endpoint: str = "http://localhost:9000/introspect"
    mcp_scope: str = "user"
    oauth_strict: bool = False

# --- 2. 공통 비즈니스 로직 (Tools) ---
# 여러 리소스 서버에서 재사용할 수 있도록 순수 함수로 분리합니다.
async def tool_get_time() -> dict[str, str | float]:
    """Get the current server time (보호된 자원 예시)."""
    now = datetime.datetime.now()
    return {
        "current_time": now.isoformat(),
        "timezone": "UTC",
        "timestamp": now.timestamp(),
        "formatted": now.strftime("%Y-%m-%d %H:%M:%S"),
    }

# 공통 인가 설정 인스턴스
default_auth_settings = SimpleAuthSettings()