# anchor.surface.mcps.server.lowlevel.helper_types
## @lineage: xphi.server.lowlevel.helper_types
## @lineage: bound.server.lowlevel.helper_types
## @lineage: bound.server.adapter.lowlevel.helper_types
## @lineage: bound.adapter.mcps.server.lowlevel.helper_types
## @lineage: bound.server.mcps.lowlevel.helper_types
## @lineage: xphi.spec.mcps.server.lowlevel.helper_types
## @lineage: xphi.spec.mcp.server.lowlevel.helper_types
from dataclasses import dataclass
from typing import Any


@dataclass
class ReadResourceContents:
    """Contents returned from a read_resource call."""

    content: str | bytes
    mime_type: str | None = None
    meta: dict[str, Any] | None = None
