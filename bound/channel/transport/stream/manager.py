# bound.channel.transport.stream.manager
## @lineage: bound.transport.stream.manager
## @lineage: bound.bridge.stream.manager
## @lineage: bound.client.bridge.stream
"""
@phase: MCP Stream Bridge
@desc: Provides unified, high-level context managers for the Agent to establish 
MCP sessions with both in-memory sandbox tools and external unauthenticated servers.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from bound.bridge.client.mcp import Client
from bound.adapter.mcps.client._transport import Transport
from watcher.plane.emitter import get_emitter

log = get_emitter("bridge.stream")

class StreamManager:
    """
    Manages the lifecycle of MCP streams for the Surgent Meta-Agent.
    Acts as the spinal cord between `agent.loop` and `gov.sandbox`.
    """

    @classmethod
    @asynccontextmanager
    async def connect_sandbox(cls, sandbox_server: Any, **kwargs: Any) -> AsyncIterator[Client]:
        """
        Connects to an internal sandbox tool (e.g., OpenHands terminal/browser)
        using a secure, zero-network In-Memory transport.
        
        Args:
            sandbox_server: An object satisfying the LowLevelServerProtocol.
        """
        log.debug("Establishing In-Memory stream to Sandbox execution environment...")
        
        # 내부적으로 InMemoryTransport를 거쳐 안전하게 세션이 열림
        async with Client(server=sandbox_server, **kwargs) as client:
            yield client

    @classmethod
    @asynccontextmanager
    async def connect_remote(cls, url: str, **kwargs: Any) -> AsyncIterator[Client]:
        """
        Connects to an external, unauthenticated MCP server via Streamable HTTP/SSE.
        """
        log.debug(f"Establishing network stream to remote MCP server: {url}")
        
        # URL 문자열이 들어오면 Client 내부에서 자동으로 streamable_http 또는 sse 로 분기
        async with Client(server=url, **kwargs) as client:
            yield client

    @classmethod
    @asynccontextmanager
    async def connect_transport(cls, transport: Transport, **kwargs: Any) -> AsyncIterator[Client]:
        """Connects using an already established Transport"""
        log.debug("Establishing session over injected Transport stream...")
        async with Client(server=transport, **kwargs) as client:
            yield client