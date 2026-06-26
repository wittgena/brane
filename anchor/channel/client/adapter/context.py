# anchor.channel.client.adapter.context
## @lineage: bound.channel.client.adapter.context
## @lineage: bound.adapter.mcps.client.context
## @lineage: xphi.mcps.client.context
## @lineage: mcps.client.context
## @lineage: anchor.surface.mcpserver.client.context
## @lineage: bound.server.client.context
## @lineage: xphi.spec.mcps.client.context
## @lineage: xphi.spec.mcp.client.context
"""Request context for MCP client handlers."""

from anchor.channel.client.adapter.session import ClientRequestContext

__all__ = ["ClientRequestContext"]
