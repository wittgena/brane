# xphi.flow.embedding.__init__
## @lineage: bound.adapter.llama.embeddings.__init__
## @lineage: bound.adapter.embeddings.__init__
## @lineage: anchor.adapter.embeddings.__init__
from xphi.adapter.llama.base.embeddings.base import BaseEmbedding
from xphi.flow.embedding.mock_embed_model import MockEmbedding
from xphi.flow.embedding.mock_embed_model import MockMultiModalEmbedding
from xphi.flow.embedding.multi_modal_base import MultiModalEmbedding
from xphi.flow.embedding.pooling import Pooling
from xphi.flow.embedding.utils import resolve_embed_model

__all__ = [
    "BaseEmbedding",
    "MockEmbedding",
    "MultiModalEmbedding",
    "MockMultiModalEmbedding",
    "Pooling",
    "resolve_embed_model",
]
