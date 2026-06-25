# bound.server.adapter.auth.errors
## @lineage: bound.adapter.mcps.server.auth.errors
## @lineage: anchor.surface.mcps.server.auth.errors
## @lineage: bound.server.mcps.auth.errors
## @lineage: xphi.spec.mcps.server.auth.errors
## @lineage: xphi.spec.mcp.server.auth.errors
from pydantic import ValidationError


def stringify_pydantic_error(validation_error: ValidationError) -> str:
    return "\n".join(f"{'.'.join(str(loc) for loc in e['loc'])}: {e['msg']}" for e in validation_error.errors())
