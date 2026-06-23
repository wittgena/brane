# bound.adapter.mcps.stdio.__main__
## @lineage: anchor.surface.mcps.stdio.__main__
## @lineage: bound.server.mcps.__main__
## @lineage: xphi.spec.mcps.server.__main__
## @lineage: xphi.spec.mcp.server.__main__
import logging
import sys
import warnings

import anyio

from bound.adapter.mcps.server.lowlevel.server import Server
from bound.adapter.mcps.stdio.server import stdio_server

if not sys.warnoptions:
    warnings.simplefilter("ignore")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("server")


async def main() -> None:
    server: Server[dict[str, object]] = Server("mcp")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    anyio.run(main, backend="trio")
