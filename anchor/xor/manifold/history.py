# anchor.xor.manifold.history
## @lineage: meta.xor.manifold.acid.history
## @lineage: meta.xor.adapter.manifold.acid.history
## @lineage: xor.adapter.manifold.acid.history
## @lineage: xor.adapter.acid.history
from typing import Any
import pydantic

class History(pydantic.BaseModel):
    messages: list[dict[str, Any]]
    model_config = pydantic.ConfigDict(
        frozen=True,
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="forbid",
    )
