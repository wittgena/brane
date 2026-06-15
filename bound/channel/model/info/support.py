# bound.channel.model.info.support
## @lineage: channel.model.info.support
from typing import Optional, Literal, List, Dict

from anchor.config.resolver import config

from bound.channel.model.cost.map import model_cost, _get_model_info_helper
from bound.channel.model.provider.resolver import get_llm_provider
from bound.channel.model.provider.manager import get_provider_info
from bound.channel.model.info.openai_params import get_supported_openai_params

from watcher.plane.emitter import get_emitter

log = get_emitter("info.support")

def supports_httpx_timeout(custom_llm_provider: str) -> bool:
    supported_providers = ["openai"]
    if custom_llm_provider in supported_providers:
        return True
    return False

def supports_system_messages(model: str, custom_llm_provider: Optional[str]) -> bool:
    return _supports_factory(
        model=model,
        custom_llm_provider=custom_llm_provider,
        key="supports_system_messages",
    )

def supports_web_search(model: str, custom_llm_provider: Optional[str] = None) -> bool:
    return _supports_factory(
        model=model,
        custom_llm_provider=custom_llm_provider,
        key="supports_web_search",
    )

def supports_url_context(model: str, custom_llm_provider: Optional[str] = None) -> bool:
    return _supports_factory(
        model=model,
        custom_llm_provider=custom_llm_provider,
        key="supports_url_context",
    )

def supports_native_streaming(model: str, custom_llm_provider: Optional[str]) -> bool:
    try:
        model, custom_llm_provider, _, _ = get_llm_provider(model=model, custom_llm_provider=custom_llm_provider)
        model_info = _get_model_info_helper(model=model, custom_llm_provider=custom_llm_provider)
        supports_native_streaming = model_info.get("supports_native_streaming", True)
        if supports_native_streaming is None:
            supports_native_streaming = True
        return supports_native_streaming
    except Exception as e:
        log.debug(
            f"Model not found or error in checking supports_native_streaming support. You passed model={model}, custom_llm_provider={custom_llm_provider}. Error: {str(e)}"
        )
        return False

def supports_response_schema(
    model: str, custom_llm_provider: Optional[str] = None
) -> bool:
    try:
        model, custom_llm_provider, _, _ = get_llm_provider(model=model, custom_llm_provider=custom_llm_provider)
    except Exception as e:
        log.debug(f"Model not found or error in checking response schema support. You passed model={model}, custom_llm_provider={custom_llm_provider}. Error: {str(e)}")
        return False
    return _supports_factory(
        model=model,
        custom_llm_provider=custom_llm_provider,
        key="supports_response_schema",
    )

def supports_parallel_function_calling(
    model: str, custom_llm_provider: Optional[str] = None
) -> bool:
    return _supports_factory(
        model=model,
        custom_llm_provider=custom_llm_provider,
        key="supports_parallel_function_calling",
    )

def supports_function_calling(
    model: str, custom_llm_provider: Optional[str] = None
) -> bool:
    return _supports_factory(
        model=model,
        custom_llm_provider=custom_llm_provider,
        key="supports_function_calling",
    )

def supports_tool_choice(model: str, custom_llm_provider: Optional[str] = None) -> bool:
    return _supports_factory(
        model=model, custom_llm_provider=custom_llm_provider, key="supports_tool_choice"
    )

def _supports_provider_info_factory(
    model: str, custom_llm_provider: Optional[str], key: str
) -> Optional[Literal[True]]:
    provider_info = get_provider_info(model=model, custom_llm_provider=custom_llm_provider)
    if provider_info is not None and provider_info.get(key, False) is True:
        return True
    return None

def _supports_factory(model: str, custom_llm_provider: Optional[str], key: str) -> bool:
    try:
        model, custom_llm_provider, _, _ = get_llm_provider(model=model, custom_llm_provider=custom_llm_provider)
        model_info = _get_model_info_helper(model=model, custom_llm_provider=custom_llm_provider)
        if model_info.get(key, False) is True:
            return True
        elif model_info.get(key) is None:  # don't check if 'False' explicitly set
            bare_model_key = _get_model_cost_key(model)
            if bare_model_key is not None:
                bare_entry = model_cost.get(bare_model_key) or {}
                if bare_entry.get(key, False) is True:
                    return True

            supported_by_provider = _supports_provider_info_factory(
                model, custom_llm_provider, key
            )
            if supported_by_provider is not None:
                return supported_by_provider

        return False
    except Exception as e:
        log.debug(f"Model not found or error in checking {key} support. You passed model={model}, custom_llm_provider={custom_llm_provider}. Error: {str(e)}")
        supported_by_provider = _supports_provider_info_factory(
            model, custom_llm_provider, key
        )
        if supported_by_provider is not None:
            return supported_by_provider

        return False

def supports_audio_input(model: str, custom_llm_provider: Optional[str] = None) -> bool:
    return _supports_factory(
        model=model, custom_llm_provider=custom_llm_provider, key="supports_audio_input"
    )

def supports_pdf_input(model: str, custom_llm_provider: Optional[str] = None) -> bool:
    return _supports_factory(
        model=model, custom_llm_provider=custom_llm_provider, key="supports_pdf_input"
    )

def supports_audio_output(
    model: str, custom_llm_provider: Optional[str] = None
) -> bool:
    return _supports_factory(
        model=model, custom_llm_provider=custom_llm_provider, key="supports_audio_output"
    )

def supports_prompt_caching(
    model: str, custom_llm_provider: Optional[str] = None
) -> bool:
    return _supports_factory(
        model=model,
        custom_llm_provider=custom_llm_provider,
        key="supports_prompt_caching",
    )

def supports_computer_use(
    model: str, custom_llm_provider: Optional[str] = None
) -> bool:
    return _supports_factory(
        model=model,
        custom_llm_provider=custom_llm_provider,
        key="supports_computer_use",
    )

def supports_vision(model: str, custom_llm_provider: Optional[str] = None) -> bool:
    return _supports_factory(
        model=model,
        custom_llm_provider=custom_llm_provider,
        key="supports_vision",
    )


def supports_reasoning(model: str, custom_llm_provider: Optional[str] = None) -> bool:
    return _supports_factory(
        model=model, custom_llm_provider=custom_llm_provider, key="supports_reasoning"
    )

def supports_native_structured_output(
    model: str, custom_llm_provider: Optional[str] = None
) -> bool:
    return _supports_factory(
        model=model,
        custom_llm_provider=custom_llm_provider,
        key="supports_native_structured_output",
    )

def get_supported_regions(
    model: str, custom_llm_provider: Optional[str] = None
) -> Optional[List[str]]:
    try:
        model, custom_llm_provider, _, _ = get_llm_provider(model=model, custom_llm_provider=custom_llm_provider)
        model_info = _get_model_info_helper(model=model, custom_llm_provider=custom_llm_provider)
        model_key = model_info.get("key")
        if model_key is None:
            return None

        model_cost_data = model_cost.get(model_key, {})
        supported_regions = model_cost_data.get("supported_regions", None)
        if supported_regions is None:
            return None

        if isinstance(supported_regions, list):
            return supported_regions
        else:
            return None
    except Exception as e:
        log.debug(
            f"Model not found or error in checking supported_regions support. You passed model={model}, custom_llm_provider={custom_llm_provider}. Error: {str(e)}"
        )
        return None


def supports_embedding_image_input(
    model: str, custom_llm_provider: Optional[str] = None
) -> bool:
    return _supports_factory(
        model=model,
        custom_llm_provider=custom_llm_provider,
        key="supports_embedding_image_input",
    )

def _get_model_cost_key(potential_key: str) -> Optional[str]:
    global _model_cost_lowercase_map

    if potential_key in litellm.model_cost:
        return potential_key

    if _model_cost_lowercase_map is None:
        _model_cost_lowercase_map = _rebuild_model_cost_lowercase_map()

    potential_key_lower = potential_key.lower()
    matched_key = _model_cost_lowercase_map.get(potential_key_lower)
    if matched_key is not None and matched_key in litellm.model_cost:
        return matched_key

    if matched_key is not None:
        matched_key = _handle_stale_map_entry_rebuild(potential_key_lower)
        if matched_key is not None:
            return matched_key

    return None

def _rebuild_model_cost_lowercase_map() -> Dict[str, str]:
    global _model_cost_lowercase_map
    _model_cost_lowercase_map = {k.lower(): k for k in litellm.model_cost}
    return _model_cost_lowercase_map

def _handle_stale_map_entry_rebuild(
    potential_key_lower: str,
) -> Optional[str]:
    global _model_cost_lowercase_map
    _model_cost_lowercase_map = _rebuild_model_cost_lowercase_map()
    matched_key = _model_cost_lowercase_map.get(potential_key_lower)
    if matched_key is not None and matched_key in litellm.model_cost:
        return matched_key
    return None