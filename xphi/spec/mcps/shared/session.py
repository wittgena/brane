# xphi.spec.mcps.shared.session
## @lineage: xphi.spec.mcp.shared.session
"""Compatibility names that outlived the removed v1 session layer (`BaseSession`)."""

from typing import Generic, TypeVar

from xphi.spec.mcps.shared.dispatcher import ProgressFnT as ProgressFnT
from xphi.spec.mcps.shared.message import MessageMetadata
from xphi.spec.mcps.types import RequestParamsMeta

RequestId = str | int

ReceiveRequestT = TypeVar("ReceiveRequestT")
SendResultT = TypeVar("SendResultT")


class RequestResponder(Generic[ReceiveRequestT, SendResultT]):
    """Typing stub for the v1 responder; the SDK never instantiates it."""

    request_id: RequestId
    request_meta: RequestParamsMeta | None
    request: ReceiveRequestT
    message_metadata: MessageMetadata
