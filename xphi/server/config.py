# xphi.server.config
## @lineage: bound.server.xphi.config
from typing import TypedDict, Any, Literal
from xphi.server.stream.http import EventStore

class ServerRunConfig(TypedDict, total=False):
    transport: Literal["stdio", "sse", "streamable-http"]
    port: int
    event_store: EventStore | None
    retry_interval: int
    uvicorn_kwargs: dict[str, Any]