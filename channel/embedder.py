# channel.embedder
from typing import Any, Callable
import numpy as np
from channel.bound.config.resolver import config
from channel.bound.embedding import embedding, aembedding
from channel.resource.cache import request_cache

class Embedder:
    def __init__(self, model: str | Callable, batch_size: int = 200, caching: bool = True, **kwargs: dict[str, Any]):
        self.model = model
        self.batch_size = batch_size
        self.caching = caching
        self.default_kwargs = kwargs

    def _preprocess(self, inputs, batch_size=None, caching=None, **kwargs):
        if isinstance(inputs, str):
            is_single_input = True
            inputs = [inputs]
        else:
            is_single_input = False

        if not all(isinstance(inp, str) for inp in inputs):
            raise ValueError("All inputs must be strings.")

        batch_size = batch_size or self.batch_size
        caching = caching or self.caching
        merged_kwargs = self.default_kwargs.copy()
        merged_kwargs.update(kwargs)

        input_batches = []
        for i in range(0, len(inputs), batch_size):
            input_batches.append(inputs[i : i + batch_size])

        return input_batches, caching, merged_kwargs, is_single_input

    def _postprocess(self, embeddings_list, is_single_input):
        embeddings = np.array(embeddings_list, dtype=np.float32)
        if is_single_input:
            return embeddings[0]
        else:
            return np.array(embeddings, dtype=np.float32)

    def __call__(self, inputs: str | list[str], batch_size: int | None = None, caching: bool | None = None, **kwargs: dict[str, Any]) -> np.ndarray:
        input_batches, caching, kwargs, is_single_input = self._preprocess(inputs, batch_size, caching, **kwargs)
        compute_embeddings = _cached_compute_embeddings if caching else _compute_embeddings
        embeddings_list = []
        for batch in input_batches:
            embeddings_list.extend(compute_embeddings(self.model, batch, caching=caching, **kwargs))
        return self._postprocess(embeddings_list, is_single_input)

    async def acall(self, inputs, batch_size=None, caching=None, **kwargs):
        input_batches, caching, kwargs, is_single_input = self._preprocess(inputs, batch_size, caching, **kwargs)

        embeddings_list = []
        acompute_embeddings = _cached_acompute_embeddings if caching else _acompute_embeddings

        for batch in input_batches:
            embeddings_list.extend(await acompute_embeddings(self.model, batch, caching=caching, **kwargs))
        return self._postprocess(embeddings_list, is_single_input)


def _compute_embeddings(model, batch_inputs, caching=False, **kwargs):
    if isinstance(model, str):
        caching = caching and config.cache is not None
        embedding_response = embedding(model=model, input=batch_inputs, caching=caching, **kwargs)
        return [data["embedding"] for data in embedding_response.data]
    elif callable(model):
        return model(batch_inputs, **kwargs)
    else:
        raise ValueError(f"`model` in `Embedder` must be a string or a callable, but got {type(model)}.")


@request_cache(ignored_args_for_cache_key=["api_key", "api_base", "base_url"])
def _cached_compute_embeddings(model, batch_inputs, caching=True, **kwargs):
    return _compute_embeddings(model, batch_inputs, caching=caching, **kwargs)


async def _acompute_embeddings(model, batch_inputs, caching=False, **kwargs):
    if isinstance(model, str):
        caching = caching and config.cache is not None
        embedding_response = await aembedding(model=model, input=batch_inputs, caching=caching, **kwargs)
        return [data["embedding"] for data in embedding_response.data]
    elif callable(model):
        return model(batch_inputs, **kwargs)
    else:
        raise ValueError(f"`model` in `Embedder` must be a string or a callable, but got {type(model)}.")


@request_cache(ignored_args_for_cache_key=["api_key", "api_base", "base_url"])
async def _cached_acompute_embeddings(model, batch_inputs, caching=True, **kwargs):
    return await _acompute_embeddings(model, batch_inputs, caching=caching, **kwargs)
