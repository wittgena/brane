# xphi.spec.mcps.client.auth.exceptions
## @lineage: xphi.spec.mcp.client.auth.exceptions
class OAuthFlowError(Exception):
    """Base exception for OAuth flow errors."""


class OAuthTokenError(OAuthFlowError):
    """Raised when token operations fail."""


class OAuthRegistrationError(OAuthFlowError):
    """Raised when client registration fails."""
