# xphi.server.auth.handlers.metadata
## @lineage: bound.server.auth.handlers.metadata
## @lineage: bound.server.adapter.auth.handlers.metadata
## @lineage: bound.adapter.mcps.server.auth.handlers.metadata
## @lineage: anchor.surface.mcps.server.auth.handlers.metadata
## @lineage: bound.server.mcps.auth.handlers.metadata
## @lineage: xphi.spec.mcps.server.auth.handlers.metadata
## @lineage: xphi.spec.mcp.server.auth.handlers.metadata
from dataclasses import dataclass

from starlette.requests import Request
from starlette.responses import Response

from xphi.server.auth.json_response import PydanticJSONResponse
from anchor.surface.mcps.shared.auth import OAuthMetadata, ProtectedResourceMetadata


@dataclass
class MetadataHandler:
    metadata: OAuthMetadata

    async def handle(self, request: Request) -> Response:
        return PydanticJSONResponse(
            content=self.metadata,
            headers={"Cache-Control": "public, max-age=3600"},  # Cache for 1 hour
        )


@dataclass
class ProtectedResourceMetadataHandler:
    metadata: ProtectedResourceMetadata

    async def handle(self, request: Request) -> Response:
        return PydanticJSONResponse(
            content=self.metadata,
            headers={"Cache-Control": "public, max-age=3600"},  # Cache for 1 hour
        )
