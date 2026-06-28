# anchor.channel.client.mcp
"""Unified MCP Client that wraps ClientSession with transport management."""
from __future__ import annotations
from contextlib import AsyncExitStack
from dataclasses import KW_ONLY, dataclass, field
from typing import Any

from anchor.surface.mcps.client._memory import InMemoryTransport
from anchor.surface.mcps.client._transport import Transport
from anchor.surface.mcps.client.session import ClientSession, ElicitationFnT, ListRootsFnT, LoggingFnT, MessageHandlerFnT, SamplingFnT
from anchor.surface.mcps.client.streamable_http import streamable_http_client

from anchor.surface.mcps.shared.dispatcher import ProgressFnT
from anchor.surface.mcps.types import (
    CallToolResult,
    CompleteResult,
    EmptyResult,
    GetPromptResult,
    Implementation,
    InitializeResult,
    ListPromptsResult,
    ListResourcesResult,
    ListResourceTemplatesResult,
    ListToolsResult,
    LoggingLevel,
    PaginatedRequestParams,
    PromptReference,
    ReadResourceResult,
    RequestParamsMeta,
    ResourceTemplateReference,
)


@dataclass
class Client:
    server: Any | Transport | str
    _: KW_ONLY

    raise_exceptions: bool = False
    """Whether to raise exceptions from the server."""

    read_timeout_seconds: float | None = None
    """Timeout for read operations."""

    sampling_callback: SamplingFnT | None = None
    """Callback for handling sampling requests."""

    list_roots_callback: ListRootsFnT | None = None
    """Callback for handling list roots requests."""

    logging_callback: LoggingFnT | None = None
    """Callback for handling logging notifications."""

    message_handler: MessageHandlerFnT | None = None
    """Callback for handling raw messages."""

    client_info: Implementation | None = None
    """Client implementation info to send to server."""

    elicitation_callback: ElicitationFnT | None = None
    """Callback for handling elicitation requests."""

    _session: ClientSession | None = field(init=False, default=None)
    _exit_stack: AsyncExitStack | None = field(init=False, default=None)
    _transport: Transport = field(init=False)

    def __post_init__(self) -> None:
        if isinstance(self.server, str):
            self._transport = streamable_http_client(self.server)
        elif isinstance(self.server, Transport):
            self._transport = self.server
        else:
            ## 나머지는 InMemoryTransport로 위임 (내부에서 hasattr로 검사됨)
            self._transport = InMemoryTransport(self.server, raise_exceptions=self.raise_exceptions)

        # if isinstance(self.server, Server | MCPServer):
        #     self._transport = InMemoryTransport(self.server, raise_exceptions=self.raise_exceptions)
        # elif isinstance(self.server, str):
        #     self._transport = streamable_http_client(self.server)
        # else:
        #     self._transport = self.server

    async def __aenter__(self) -> Client:
        """Enter the async context manager."""
        if self._session is not None:
            raise RuntimeError("Client is already entered; cannot reenter")

        async with AsyncExitStack() as exit_stack:
            read_stream, write_stream = await exit_stack.enter_async_context(self._transport)

            self._session = await exit_stack.enter_async_context(
                ClientSession(
                    read_stream=read_stream,
                    write_stream=write_stream,
                    read_timeout_seconds=self.read_timeout_seconds,
                    sampling_callback=self.sampling_callback,
                    list_roots_callback=self.list_roots_callback,
                    logging_callback=self.logging_callback,
                    message_handler=self.message_handler,
                    client_info=self.client_info,
                    elicitation_callback=self.elicitation_callback,
                )
            )

            await self._session.initialize()

            # Transfer ownership to self for __aexit__ to handle
            self._exit_stack = exit_stack.pop_all()
            return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: Any) -> None:
        """Exit the async context manager."""
        if self._exit_stack:  # pragma: no branch
            await self._exit_stack.__aexit__(exc_type, exc_val, exc_tb)
        self._session = None

    @property
    def session(self) -> ClientSession:
        """Get the underlying ClientSession.

        This provides access to the full ClientSession API for advanced use cases.

        Raises:
            RuntimeError: If accessed before entering the context manager.
        """
        if self._session is None:
            raise RuntimeError("Client must be used within an async context manager")
        return self._session

    @property
    def initialize_result(self) -> InitializeResult:
        """The server's InitializeResult.

        Contains server_info, capabilities, instructions, and the negotiated protocol_version.
        Raises RuntimeError if accessed outside the context manager.
        """
        result = self.session.initialize_result
        if result is None:  # pragma: no cover
            raise RuntimeError("Client must be used within an async context manager")
        return result

    async def send_ping(self, *, meta: RequestParamsMeta | None = None) -> EmptyResult:
        """Send a ping request to the server."""
        return await self.session.send_ping(meta=meta)

    async def send_progress_notification(
        self,
        progress_token: str | int,
        progress: float,
        total: float | None = None,
        message: str | None = None,
    ) -> None:
        """Send a progress notification to the server."""
        await self.session.send_progress_notification(
            progress_token=progress_token,
            progress=progress,
            total=total,
            message=message,
        )

    async def set_logging_level(self, level: LoggingLevel, *, meta: RequestParamsMeta | None = None) -> EmptyResult:
        """Set the logging level on the server."""
        return await self.session.set_logging_level(level=level, meta=meta)

    async def list_resources(
        self,
        *,
        cursor: str | None = None,
        meta: RequestParamsMeta | None = None,
    ) -> ListResourcesResult:
        """List available resources from the server."""
        return await self.session.list_resources(params=PaginatedRequestParams(cursor=cursor, _meta=meta))

    async def list_resource_templates(
        self,
        *,
        cursor: str | None = None,
        meta: RequestParamsMeta | None = None,
    ) -> ListResourceTemplatesResult:
        """List available resource templates from the server."""
        return await self.session.list_resource_templates(params=PaginatedRequestParams(cursor=cursor, _meta=meta))

    async def read_resource(self, uri: str, *, meta: RequestParamsMeta | None = None) -> ReadResourceResult:
        return await self.session.read_resource(uri, meta=meta)

    async def subscribe_resource(self, uri: str, *, meta: RequestParamsMeta | None = None) -> EmptyResult:
        """Subscribe to resource updates."""
        return await self.session.subscribe_resource(uri, meta=meta)

    async def unsubscribe_resource(self, uri: str, *, meta: RequestParamsMeta | None = None) -> EmptyResult:
        """Unsubscribe from resource updates."""
        return await self.session.unsubscribe_resource(uri, meta=meta)

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        read_timeout_seconds: float | None = None,
        progress_callback: ProgressFnT | None = None,
        *,
        meta: RequestParamsMeta | None = None,
    ) -> CallToolResult:
        return await self.session.call_tool(
            name=name,
            arguments=arguments,
            read_timeout_seconds=read_timeout_seconds,
            progress_callback=progress_callback,
            meta=meta,
        )

    async def list_prompts(
        self,
        *,
        cursor: str | None = None,
        meta: RequestParamsMeta | None = None,
    ) -> ListPromptsResult:
        """List available prompts from the server."""
        return await self.session.list_prompts(params=PaginatedRequestParams(cursor=cursor, _meta=meta))

    async def get_prompt(
        self, name: str, arguments: dict[str, str] | None = None, *, meta: RequestParamsMeta | None = None
    ) -> GetPromptResult:
        return await self.session.get_prompt(name=name, arguments=arguments, meta=meta)

    async def complete(
        self,
        ref: ResourceTemplateReference | PromptReference,
        argument: dict[str, str],
        context_arguments: dict[str, str] | None = None,
    ) -> CompleteResult:
        return await self.session.complete(ref=ref, argument=argument, context_arguments=context_arguments)

    async def list_tools(self, *, cursor: str | None = None, meta: RequestParamsMeta | None = None) -> ListToolsResult:
        """List available tools from the server."""
        return await self.session.list_tools(params=PaginatedRequestParams(cursor=cursor, _meta=meta))

    async def send_roots_list_changed(self) -> None:
        """Send a notification that the roots list has changed."""
        await self.session.send_roots_list_changed()
