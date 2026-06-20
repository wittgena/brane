# xphi.spec.mcps.server.pagination.__main__
## @lineage: xphi.spec.mcp.server.pagination.__main__
import sys

from .server import main

sys.exit(main())  # type: ignore[call-arg]
