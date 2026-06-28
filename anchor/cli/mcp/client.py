# anchor.cli.mcp.client
## @lineage: anchor.cli.mcps.client
import argparse
import sys
import warnings
from functools import partial
from urllib.parse import urlparse
import anyio

from mcp_types import ServerRequest, ClientResult, ServerNotification, Implementation
from mcp.shared.message import SessionMessage
from mcp.shared.session import RequestResponder

from anchor.surface.mcps.client._transport import ReadStream, WriteStream
from anchor.surface.mcps.client.session import ClientSession
from anchor.surface.mcps.client.sse import sse_client
from anchor.surface.mcps.client.stdio import StdioServerParameters, stdio_client


from watcher.plane.emitter import get_emitter

if not sys.warnoptions:
    warnings.simplefilter("ignore")

log = get_emitter("mcps.client")


async def message_handler(
    message: RequestResponder[ServerRequest, ClientResult] | ServerNotification | Exception,
) -> None:
    if isinstance(message, Exception):
        log.error("Error: %s", message)
        return

    log.info("Received message from server: %s", message)


async def run_session(
    read_stream: ReadStream[SessionMessage | Exception],
    write_stream: WriteStream[SessionMessage],
    client_info: Implementation | None = None,
):
    async with ClientSession(
        read_stream,
        write_stream,
        message_handler=message_handler,
        client_info=client_info,
    ) as session:
        log.info("Initializing session")
        await session.initialize()
        log.info("Initialized")


async def main(command_or_url: str, args: list[str], env: list[tuple[str, str]]):
    env_dict = dict(env)

    if urlparse(command_or_url).scheme in ("http", "https"):
        # Use SSE client for HTTP(S) URLs
        async with sse_client(command_or_url) as streams:
            await run_session(*streams)
    else:
        # Use stdio client for commands
        server_parameters = StdioServerParameters(command=command_or_url, args=args, env=env_dict)
        async with stdio_client(server_parameters) as streams:
            await run_session(*streams)


def cli():
    parser = argparse.ArgumentParser()
    parser.add_argument("command_or_url", help="Command or URL to connect to")
    parser.add_argument("args", nargs="*", help="Additional arguments")
    parser.add_argument(
        "-e",
        "--env",
        nargs=2,
        action="append",
        metavar=("KEY", "VALUE"),
        help="Environment variables to set. Can be used multiple times.",
        default=[],
    )

    args = parser.parse_args()
    anyio.run(partial(main, args.command_or_url, args.args, args.env), backend="trio")

if __name__ == "__main__":
    cli()
