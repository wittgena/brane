# xphi.server.router.auth
## @lineage: bound.bridge.server.broker
## @lineage: xphi.server.auth.xphi.broker
import time
from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from anchor.surface.mcps.server.auth.routes import cors_middleware, create_auth_routes
from anchor.surface.mcps.server.auth.settings import AuthSettings, ClientRegistrationOptions
from xphi.server.handle.auth import SimpleOAuthProvider
from xphi.server.setting import AuthServerSettings, default_auth_settings

settings = AuthServerSettings()

class SimpleAuthProvider(SimpleOAuthProvider):
    def __init__(self):
        super().__init__(default_auth_settings, settings.auth_callback_path, str(settings.server_url))

provider = SimpleAuthProvider()

mcp_auth_settings = AuthSettings(
    issuer_url=settings.server_url,
    client_registration_options=ClientRegistrationOptions(
        enabled=True,
        valid_scopes=[default_auth_settings.mcp_scope],
        default_scopes=[default_auth_settings.mcp_scope],
    ),
    required_scopes=[default_auth_settings.mcp_scope],
    resource_server_url=None,
)

# 라우트 설정
routes = create_auth_routes(
    provider=provider,
    issuer_url=mcp_auth_settings.issuer_url,
    service_documentation_url=mcp_auth_settings.service_documentation_url,
    client_registration_options=mcp_auth_settings.client_registration_options,
    revocation_options=mcp_auth_settings.revocation_options,
)

async def login_page(request: Request) -> Response:
    state = request.query_params.get("state")
    if not state: raise HTTPException(400, "Missing state parameter")
    return await provider.get_login_page(state)

async def login_callback(request: Request) -> Response:
    return await provider.handle_login_callback(request)

async def introspect(request: Request) -> Response:
    """리소스 서버(MCP)들이 토큰을 검증하기 위해 호출하는 엔드포인트"""
    form = await request.form()
    token = form.get("token")
    if not token or not isinstance(token, str):
        return JSONResponse({"active": False}, status_code=400)

    access_token = await provider.load_access_token(token)
    if not access_token:
        return JSONResponse({"active": False})

    return JSONResponse({
        "active": True,
        "client_id": access_token.client_id,
        "scope": " ".join(access_token.scopes),
        "exp": access_token.expires_at,
        "iat": int(time.time()),
        "token_type": "Bearer",
        "sub": access_token.subject,
        "iss": str(settings.server_url),
    })

routes.extend([
    Route("/login", endpoint=login_page, methods=["GET"]),
    Route("/login/callback", endpoint=login_callback, methods=["POST"]),
    Route("/introspect", endpoint=cors_middleware(introspect, ["POST", "OPTIONS"]), methods=["POST", "OPTIONS"]),
])

# ASGI Application (uvicorn으로 바로 실행 가능)
app = Starlette(routes=routes)