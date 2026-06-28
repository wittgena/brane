# anchor.surface.mcps.client._transport
## @lineage: anchor.channel.client.adapter._transport
"""Transport protocol for MCP clients."""
from __future__ import annotations
from contextlib import AbstractAsyncContextManager
from typing import Protocol
from anchor.surface.mcps.shared._stream_protocols import ReadStream, WriteStream
from anchor.surface.mcps.shared.message import SessionMessage

__all__ = ["ReadStream", "WriteStream", "Transport", "TransportStreams"]

TransportStreams = tuple[ReadStream[SessionMessage | Exception], WriteStream[SessionMessage]]


class Transport(AbstractAsyncContextManager[TransportStreams], Protocol):
    """Protocol for MCP transports.

    A transport is an async context manager that yields read and write streams
    for bidirectional communication with an MCP server.
    """
