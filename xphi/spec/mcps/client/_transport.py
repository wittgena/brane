# xphi.spec.mcps.client._transport
## @lineage: xphi.spec.mcp.client._transport
"""Transport protocol for MCP clients."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Protocol

from xphi.spec.mcps.shared._stream_protocols import ReadStream, WriteStream
from xphi.spec.mcps.shared.message import SessionMessage

__all__ = ["ReadStream", "WriteStream", "Transport", "TransportStreams"]

TransportStreams = tuple[ReadStream[SessionMessage | Exception], WriteStream[SessionMessage]]


class Transport(AbstractAsyncContextManager[TransportStreams], Protocol):
    """Protocol for MCP transports.

    A transport is an async context manager that yields read and write streams
    for bidirectional communication with an MCP server.
    """
