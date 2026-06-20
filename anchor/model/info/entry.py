# anchor.model.info.entry
## @lineage: anchor.router.model.info.entry
## @lineage: bound.router.model.info.entry
## @lineage: bound.channel.model.info.entry
## @lineage: channel.model.info.entry
from typing import Optional
from functools import lru_cache, wraps

from anchor.base.model import BaseLLMModelInfo, type_to_response_format_param
from anchor.base.config.constants import DEFAULT_MAX_LRU_CACHE_SIZE
from anchor.base.config.resolver import config

from anchor.model.router.provider.manager import get_provider_info
from anchor.model.types.utils import ModelInfo

def get_model_info(
    model: str,
    custom_llm_provider: Optional[str] = None,
    api_base: Optional[str] = None,
    api_key: Optional[str] = None,
) -> ModelInfo:
    if api_key is not None:
        return _build_model_info(model, custom_llm_provider, api_base, api_key)
    return _cached_get_model_info(model, custom_llm_provider, api_base)

def _build_model_info(
    model: str,
    custom_llm_provider: Optional[str] = None,
    api_base: Optional[str] = None,
    api_key: Optional[str] = None,
) -> ModelInfo:
    from anchor.model.cost.map import _get_model_info_helper

    supported_openai_params = config.get_supported_openai_params(
        model=model, custom_llm_provider=custom_llm_provider
    )
    _model_info = _get_model_info_helper(
        model=model,
        custom_llm_provider=custom_llm_provider,
        api_base=api_base,
        api_key=api_key,
    )
    provider_info = get_provider_info(model=model, custom_llm_provider=custom_llm_provider)
    if provider_info:
        for key, value in provider_info.items():
            if value is not None:
                _model_info[key] = value  # type: ignore
    return ModelInfo(**_model_info, supported_openai_params=supported_openai_params)

@lru_cache(maxsize=DEFAULT_MAX_LRU_CACHE_SIZE)
def _cached_get_model_info(
    model: str,
    custom_llm_provider: Optional[str] = None,
    api_base: Optional[str] = None,
) -> ModelInfo:
    return _build_model_info(model=model, custom_llm_provider=custom_llm_provider, api_base=api_base)