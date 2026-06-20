# xphi.spec.mcps.client.auth.__init__
## @lineage: xphi.spec.mcp.client.auth.__init__
"""OAuth2 Authentication implementation for HTTPX.

Implements authorization code flow with PKCE and automatic token refresh.
"""

from xphi.spec.mcps.client.auth.exceptions import OAuthFlowError, OAuthRegistrationError, OAuthTokenError
from xphi.spec.mcps.client.auth.oauth2 import (
    OAuthClientProvider,
    PKCEParameters,
    TokenStorage,
)

__all__ = [
    "OAuthClientProvider",
    "OAuthFlowError",
    "OAuthRegistrationError",
    "OAuthTokenError",
    "PKCEParameters",
    "TokenStorage",
]
