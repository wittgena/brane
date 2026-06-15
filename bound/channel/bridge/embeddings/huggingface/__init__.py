# bound.channel.bridge.embeddings.huggingface.__init__
## @lineage: channel.bridge.embeddings.huggingface.__init__
## @lineage: bridge.llama.embeddings.huggingface.__init__
from llama_index.embeddings.huggingface.base import (
    HuggingFaceEmbedding,
    HuggingFaceInferenceAPIEmbedding,
    HuggingFaceInferenceAPIEmbeddings,
)

__all__ = [
    "HuggingFaceEmbedding",
    "HuggingFaceInferenceAPIEmbedding",
    "HuggingFaceInferenceAPIEmbeddings",
]
