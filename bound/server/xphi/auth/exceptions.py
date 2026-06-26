# bound.server.xphi.auth.exceptions
## @lineage: xphi.server.auth.exceptions
## @lineage: bound.adapter.mcps.auth.exceptions
## @lineage: xphi.mcps.client.auth.exceptions
## @lineage: mcps.client.auth.exceptions
## @lineage: anchor.surface.mcpserver.client.auth.exceptions
## @lineage: bound.server.client.auth.exceptions
## @lineage: xphi.spec.mcps.client.auth.exceptions
## @lineage: xphi.spec.mcp.client.auth.exceptions
class OAuthFlowError(Exception):
    """Base exception for OAuth flow errors."""


class OAuthTokenError(OAuthFlowError):
    """Raised when token operations fail."""


class OAuthRegistrationError(OAuthFlowError):
    """Raised when client registration fails."""
