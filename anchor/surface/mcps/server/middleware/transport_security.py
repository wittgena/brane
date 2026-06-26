# anchor.surface.mcps.server.middleware.transport_security
## @lineage: xphi.server.transport.security
import logging
from pydantic import BaseModel, Field
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

class TransportSecuritySettings(BaseModel):
    enable_dns_rebinding_protection: bool = True
    allowed_hosts: list[str] = Field(default_factory=list)
    allowed_origins: list[str] = Field(default_factory=list)

class TransportSecurityMiddleware:
    def __init__(self, settings: TransportSecuritySettings | None = None):
        self.settings = settings or TransportSecuritySettings(enable_dns_rebinding_protection=False)

    def _validate_host(self, host: str | None) -> bool:
        if not host:
            logger.warning("Missing Host header in request")
            return False

        # Check exact match first
        if host in self.settings.allowed_hosts:
            return True

        # Check wildcard port patterns
        for allowed in self.settings.allowed_hosts:
            if allowed.endswith(":*"):
                # Extract base host from pattern
                base_host = allowed[:-2]
                # Check if the actual host starts with base host and has a port
                if host.startswith(base_host + ":"):
                    return True

        logger.warning(f"Invalid Host header: {host}")
        return False

    def _validate_origin(self, origin: str | None) -> bool:
        """Validate the Origin header against allowed values."""
        # Origin can be absent for same-origin requests
        if not origin:
            return True

        # Check exact match first
        if origin in self.settings.allowed_origins:
            return True

        # Check wildcard port patterns
        for allowed in self.settings.allowed_origins:
            if allowed.endswith(":*"):
                # Extract base origin from pattern
                base_origin = allowed[:-2]
                # Check if the actual origin starts with base origin and has a port
                if origin.startswith(base_origin + ":"):
                    return True

        logger.warning(f"Invalid Origin header: {origin}")
        return False

    def _validate_content_type(self, content_type: str | None) -> bool:
        """Validate the Content-Type header for POST requests."""
        return content_type is not None and content_type.lower().startswith("application/json")

    async def validate_request(self, request: Request, is_post: bool = False) -> Response | None:
        """Validate request headers for DNS rebinding protection.

        Returns None if validation passes, or an error Response if validation fails.
        """
        # Always validate Content-Type for POST requests
        if is_post:
            content_type = request.headers.get("content-type")
            if not self._validate_content_type(content_type):
                return Response("Invalid Content-Type header", status_code=400)

        # Skip remaining validation if DNS rebinding protection is disabled
        if not self.settings.enable_dns_rebinding_protection:
            return None

        # Validate Host header
        host = request.headers.get("host")
        if not self._validate_host(host):
            return Response("Invalid Host header", status_code=421)

        # Validate Origin header
        origin = request.headers.get("origin")
        if not self._validate_origin(origin):
            return Response("Invalid Origin header", status_code=403)

        return None
