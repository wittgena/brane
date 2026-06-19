# anchor.model.types.file
## @lineage: anchor.router.model.types.file
## @lineage: bound.router.model.types.file
## @lineage: bound.channel.model.types.file
## @lineage: channel.model.types.file
## @lineage: gate.model.types.file
## @lineage: gate.types.file
from typing import AsyncIterator, Dict, Iterator, Literal, NamedTuple, Union

FileContentProvider = Literal[
    "openai", "azure", "vertex_ai", "bedrock", "hosted_vllm", "anthropic", "manus"
]


class FileContentStreamingResult(NamedTuple):
    stream_iterator: Union[Iterator[bytes], AsyncIterator[bytes]]
    headers: Dict[str, str]
