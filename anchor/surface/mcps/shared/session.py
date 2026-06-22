# anchor.surface.mcps.shared.session
## @lineage: bound.server.mcps.shared.session
## @lineage: xphi.spec.mcps.shared.session
## @lineage: xphi.spec.mcp.shared.session
"""Compatibility names that outlived the removed v1 session layer (`BaseSession`)."""

from typing import Generic, TypeVar

from anchor.surface.mcps.shared.dispatcher import ProgressFnT as ProgressFnT
from anchor.surface.mcps.shared.message import MessageMetadata
from anchor.surface.mcps.types import RequestParamsMeta

RequestId = str | int

ReceiveRequestT = TypeVar("ReceiveRequestT")
SendResultT = TypeVar("SendResultT")


class RequestResponder(Generic[ReceiveRequestT, SendResultT]):
    """Typing stub for the v1 responder; the SDK never instantiates it."""

    request_id: RequestId
    request_meta: RequestParamsMeta | None
    request: ReceiveRequestT
    message_metadata: MessageMetadata
