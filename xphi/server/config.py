# xphi.server.config
## @lineage: bound.server.config
## @lineage: bound.server.mcps.config
## @lineage: anchor.mcp.server.config
# anchor.mcp.types (또는 cli.config 모듈)
from typing import TypedDict, Any, Literal
from bound.adapter.mcps.stdio.streamable_http import EventStore

class ServerRunConfig(TypedDict, total=False):
    transport: Literal["stdio", "sse", "streamable-http"]
    port: int
    event_store: EventStore | None
    retry_interval: int
    uvicorn_kwargs: dict[str, Any]