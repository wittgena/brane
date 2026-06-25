# xphi.server.config
from typing import TypedDict, Any, Literal
from bound.server.stream.http import EventStore

class ServerRunConfig(TypedDict, total=False):
    transport: Literal["stdio", "sse", "streamable-http"]
    port: int
    event_store: EventStore | None
    retry_interval: int
    uvicorn_kwargs: dict[str, Any]