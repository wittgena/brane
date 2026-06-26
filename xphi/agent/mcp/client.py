# xphi.agent.mcp.client
## @lineage: anchor.agent.mcp.client
## @lineage: gov.protocol.mcp.client
import asyncio
import inspect
from collections.abc import Callable
from typing import Any
from fastmcp import Client as AsyncMCPClient

from xphi.agent.mcp.exception import MCPError
from arch.proto.wrapper.asyncer import AsyncExecutor

class MCPClient(AsyncMCPClient):
    _executor: AsyncExecutor
    _closed: bool

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._executor = AsyncExecutor()
        self._closed = False

    async def connect(self) -> None:
        try:
            await self.__aenter__()
        except RuntimeError as exc:
            raise MCPError("MCP Connection Failure") from exc

    def call_async_from_sync(self, awaitable_or_fn: Callable[..., Any] | Any, *args, timeout: float, **kwargs) -> Any:
        return self._executor.run_async(awaitable_or_fn, *args, timeout=timeout, **kwargs)

    async def call_sync_from_async(self, fn: Callable[..., Any], *args, **kwargs) -> Any:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))

    def sync_close(self) -> None:
        if self._closed:
            return
        if hasattr(self, "close") and inspect.iscoroutinefunction(self.close):
            try:
                self._executor.run_async(self.close, timeout=10.0)
            except Exception:
                pass
        self._executor.close()
        self._closed = True

    def __del__(self):
        try:
            self.sync_close()
        except Exception:
            pass

    def __enter__(self) -> "MCPClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.sync_close()