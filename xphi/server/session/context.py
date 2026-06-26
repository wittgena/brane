# xphi.server.session.context
## @lineage: bound.conn.server.context
## @lineage: bound.server.conn.context
## @lineage: bound.adapter.mcps.stdio.context
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, Generic, Protocol

from pydantic import BaseModel
from typing_extensions import TypeVar

from xphi.server.session.connection import Connection
from xphi.server.session.session import ServerSession
from anchor.surface.mcps.shared.context import BaseContext
from anchor.surface.mcps.shared.dispatcher import DispatchContext
from anchor.surface.mcps.shared.message import CloseSSEStreamCallback
from anchor.surface.mcps.shared.peer import Meta
from anchor.surface.mcps.shared.transport_context import TransportContext
from anchor.surface.mcps.types import LoggingLevel, RequestId, RequestParamsMeta

LifespanContextT = TypeVar("LifespanContextT", default=dict[str, Any])
RequestT = TypeVar("RequestT", default=Any)

@dataclass(kw_only=True)
class ServerRequestContext(Generic[LifespanContextT, RequestT]):
    session: ServerSession
    lifespan_context: LifespanContextT
    request_id: RequestId | None = None
    meta: RequestParamsMeta | None = None
    request: RequestT | None = None
    close_sse_stream: CloseSSEStreamCallback | None = None
    close_standalone_sse_stream: CloseSSEStreamCallback | None = None


# Covariant: `lifespan` is exposed read-only, so a `Context[AppState]` passes as `Context[object]`.
LifespanT_co = TypeVar("LifespanT_co", default=Any, covariant=True)


class Context(BaseContext[TransportContext], Generic[LifespanT_co]):
    def __init__(
        self,
        dctx: DispatchContext[TransportContext],
        *,
        lifespan: LifespanT_co,
        connection: Connection,
        meta: RequestParamsMeta | None = None,
    ) -> None:
        super().__init__(dctx, meta=meta)
        self._lifespan = lifespan
        self._connection = connection

    @property
    def lifespan(self) -> LifespanT_co:
        """The server-wide lifespan output (what `Server(..., lifespan=...)` yielded)."""
        return self._lifespan

    @property
    def connection(self) -> Connection:
        """The per-client `Connection` for this request's connection."""
        return self._connection

    @property
    def session_id(self) -> str | None:
        """The transport's session id for this connection, when one exists.

        Convenience for `ctx.connection.session_id`. `None` on stdio and
        stateless HTTP.
        """
        return self._connection.session_id

    @property
    def headers(self) -> Mapping[str, str] | None:
        """Request headers carried by this message, when the transport has them.

        Convenience for `ctx.transport.headers`. `None` on stdio.
        """
        return self.transport.headers

    async def log(self, level: LoggingLevel, data: Any, logger: str | None = None, *, meta: Meta | None = None) -> None:
        """Send a request-scoped `notifications/message` log entry.

        Uses this request's back-channel (so the entry rides the request's SSE
        stream in streamable HTTP), not the standalone stream - use
        `ctx.connection.log(...)` for that.
        """
        params: dict[str, Any] = {"level": level, "data": data}
        if logger is not None:
            params["logger"] = logger
        if meta:
            params["_meta"] = meta
        await self.notify("notifications/message", params)


HandlerResult = BaseModel | dict[str, Any] | None
"""What a request handler (or middleware) may return. `ServerRunner` serializes
all three to a result dict."""

CallNext = Callable[[], Awaitable[HandlerResult]]

_MwLifespanT = TypeVar("_MwLifespanT")


class ServerMiddleware(Protocol[_MwLifespanT]):
    async def __call__(
        self,
        ctx: ServerRequestContext[_MwLifespanT, Any],
        method: str,
        params: Mapping[str, Any] | None,
        call_next: CallNext,
    ) -> HandlerResult: ...
