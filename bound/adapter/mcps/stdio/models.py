# bound.adapter.mcps.stdio.models
## @lineage: anchor.surface.mcps.stdio.models
## @lineage: bound.server.mcps.models
## @lineage: xphi.spec.mcps.server.models
## @lineage: xphi.spec.mcp.server.models
"""This module provides simplified types to use with the server for managing prompts
and tools.
"""

from pydantic import BaseModel

from anchor.surface.mcps.types import Icon, ServerCapabilities


class InitializationOptions(BaseModel):
    server_name: str
    server_version: str
    title: str | None = None
    description: str | None = None
    capabilities: ServerCapabilities
    instructions: str | None = None
    website_url: str | None = None
    icons: list[Icon] | None = None
