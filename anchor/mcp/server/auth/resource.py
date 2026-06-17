# anchor.mcp.server.auth.resource
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver.server import MCPServer
from xphi.spec.exam.auth.verifier.token import IntrospectionTokenVerifier
from anchor.mcp.server.auth.setting import ResourceServerSettings, tool_get_time
from watcher.plane.emitter import get_emitter

log = get_emitter("auth.resource")

# 1. 설정 로드 (환경 변수로 오버라이드 가능)
settings = ResourceServerSettings()

# 2. cli.tool을 위한 실행 스펙 선언
mcp_config = {
    "transport": "streamable-http",
    "port": settings.port,
    # uvicorn 추가 설정 등 필요시 여기에 작성
}

# 3. 토큰 검증기 설정 (브로커 서버를 바라봄)
token_verifier = IntrospectionTokenVerifier(
    introspection_endpoint=settings.auth_server_introspection_endpoint,
    server_url=str(settings.server_url),
    validate_resource=settings.oauth_strict,
)

# 4. 서버 인스턴스화
mcp = MCPServer(
    name="MCP Protected Resource Server",
    instructions="Resource Server that validates tokens via Broker Server introspection",
    debug=True,
    token_verifier=token_verifier,
    auth=AuthSettings(
        issuer_url=settings.auth_server_url,
        required_scopes=[settings.mcp_scope],
        resource_server_url=settings.server_url,
    ),
)

# 5. 공유 비즈니스 로직(Tool) 등록
# shared.py에서 가져온 순수 함수를 도구로 래핑합니다.
mcp.tool(name="get_time", description="Get the current server time (Protected)")(tool_get_time)