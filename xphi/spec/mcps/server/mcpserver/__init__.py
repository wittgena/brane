# xphi.spec.mcps.server.mcpserver.__init__
## @lineage: xphi.spec.mcp.server.mcpserver.__init__
"""MCPServer - A more ergonomic interface for MCP servers."""

from xphi.spec.mcps.types import Icon

from .context import Context
from .server import MCPServer
from .utilities.types import Audio, Image

__all__ = ["MCPServer", "Context", "Image", "Audio", "Icon"]
