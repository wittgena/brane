# anchor.cli.mcps.server
## @lineage: bound.adapter.mcps.server
import sys
import warnings
import anyio
from anchor.surface.mcps.server.lowlevel.server import Server
from xphi.server.stream.stdio import stdio_server
from watcher.plane.emitter import get_emitter

log = get_emitter("mcps.server")

if not sys.warnoptions:
    warnings.simplefilter("ignore")

async def main() -> None:
    server: Server[dict[str, object]] = Server("mcp")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())

if __name__ == "__main__":
    anyio.run(main, backend="trio")
