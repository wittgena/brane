# bound.agent.mcp.client
## @lineage: xphi.agent.mcp.client
import asyncio
import inspect
from collections.abc import Callable
from contextlib import AsyncExitStack
from typing import Any

from bound.agent.mcp.exception import MCPError
from bound.agent.mcp.config import MCPConfig
from arch.proto.wrapper.asyncer import AsyncExecutor

from anchor.channel.bridge.client import Client as AnchorClient
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters

class MCPClient(AnchorClient):
    """
    Unified MCP Client that bridges AnchorClient with stdio execution via MCPConfig.
    """
    _executor: AsyncExecutor
    _closed: bool
    _config: MCPConfig | None

    def __init__(self, config: MCPConfig | dict | None = None, server: Any = None, **kwargs):
        self._executor = AsyncExecutor()
        self._closed = False
        
        # 딕셔너리로 들어올 경우 내부 모델로 변환
        if isinstance(config, dict):
            config = MCPConfig.model_validate(config)
        self._config = config

        # fastmcp 호환성을 위해 남아있을 수 있는 인자 제거
        kwargs.pop("log_handler", None)

        # AnchorClient는 server 인자를 필수로 요구함.
        # config가 존재할 경우, server는 dummy 값으로 넘기고 __aenter__에서 덮어씀
        target_server = server if server is not None else "stdio_config_override"
        
        super().__init__(server=target_server, **kwargs)

    async def __aenter__(self) -> "MCPClient":
        """Enter the async context manager and establish transport."""
        if self._session is not None:
            raise RuntimeError("Client is already entered; cannot reenter")

        # Config 기반 Stdio 실행 로직
        if self._config and self._config.mcpServers:
            # 설정된 첫 번째 MCP 서버를 가져와서 실행 파라미터 구성
            server_name = list(self._config.mcpServers.keys())[0]
            server_cfg = self._config.mcpServers[server_name]
            
            server_params = StdioServerParameters(
                command=server_cfg.command,
                args=server_cfg.args,
                env=server_cfg.env
            )

            async with AsyncExitStack() as exit_stack:
                # 1. stdio_client를 통해 서브프로세스를 실행하고 입출력 스트림 획득
                read_stream, write_stream = await exit_stack.enter_async_context(
                    stdio_client(server_params)
                )

                # 2. 획득한 스트림으로 Anchor의 ClientSession 초기화
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

                # 3. Context 탈출 시 안전한 종료를 위해 스택을 객체에 위임
                self._exit_stack = exit_stack.pop_all()
                return self
        
        # Config가 없거나 기타 방식(InMemory, HTTP 등)인 경우 부모 클래스의 기본 로직 수행
        return await super().__aenter__()

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
            
        # 기존 __aexit__ 호출을 Task로 실행하여 리소스 정리
        async def _async_close():
            if self._session is not None:
                await self.__aexit__(None, None, None)

        try:
            self._executor.run_async(_async_close, timeout=10.0)
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