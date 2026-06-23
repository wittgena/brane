# anchor.model.info.cost.map
import os
import litellm
from typing import Union, cast, Optional, Dict

from anchor.base.config.resolver import config
from anchor.model.info.entry import get_model_info
from anchor.model.provider.registry import get_model_cost_map
from anchor.model.provider.types import ProviderTypes
from watcher.plane.emitter import get_emitter

log = get_emitter("cost.map")

## Load initial model cost map (SSOT)
model_cost_map_url: str = os.getenv(
    "LITELLM_MODEL_COST_MAP_URL",
    "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json",
)
model_cost, _ = get_model_cost_map(url=model_cost_map_url)

def _get_model_info_helper(
    model: str,
    custom_llm_provider: Optional[str] = None,
    api_base: Optional[str] = None,
    api_key: Optional[str] = None,
) -> dict:
    """Simplified helper returning the raw dictionary directly from the cost map."""
    potential_keys = []
    if custom_llm_provider:
        potential_keys.append(f"{custom_llm_provider}/{model}")
    potential_keys.append(model)
    
    if "/" in model:
        stripped_model = model.split("/", 1)[1]
        if custom_llm_provider:
            potential_keys.append(f"{custom_llm_provider}/{stripped_model}")
        potential_keys.append(stripped_model)

    matched_info = None
    matched_key = None

    for key in potential_keys:
        if key in model_cost:
            matched_info = model_cost[key]
            matched_key = key
            break

    if matched_info is None:
        log.warning(f"Model not mapped in model_cost. model={model}, provider={custom_llm_provider}")
        return {"key": model, "input_cost_per_token": 0.0, "output_cost_per_token": 0.0}

    result = matched_info.copy()
    result["key"] = matched_key

    ## Ensure critical cost parameters exist
    if result.get("input_cost_per_token") is None:
        result["input_cost_per_token"] = 0.0
    if result.get("output_cost_per_token") is None:
        result["output_cost_per_token"] = 0.0

    return result

def register_model(new_model_cost: Union[str, dict]):
    """Dynamically registers new model cost and metadata."""
    loaded_model_cost = {}
    if isinstance(new_model_cost, dict):
        loaded_model_cost = new_model_cost
    elif isinstance(new_model_cost, str):
        loaded_model_cost, _ = get_model_cost_map(url=new_model_cost)

    _skip_get_model_info_providers = {
        ProviderTypes.GITHUB_COPILOT.value,
        ProviderTypes.CHATGPT.value,
    }

    for key, value in loaded_model_cost.items():
        provider = value.get("litellm_provider", "")
        _key_str = str(key)
        
        if provider in _skip_get_model_info_providers or any(
            _key_str.startswith(f"{p}/") for p in _skip_get_model_info_providers
        ):
            existing_model = model_cost.get(key, {})
            model_cost_key = key
        else:
            try:
                existing_model = cast(dict, get_model_info(model=key))
                model_cost_key = existing_model.get("key", key)
            except Exception:
                existing_model = {}
                model_cost_key = key
                
        if existing_model.get("litellm_provider") is None:
            existing_model.pop("litellm_provider", None)
            
        updated_dictionary = _update_dictionary(existing_model, value)
        model_cost.setdefault(model_cost_key, {}).update(updated_dictionary)
        
        _clear_model_info_caches()

        log.debug(f"Added/updated model={model_cost_key} in model_cost")
        
        if value.get("litellm_provider") == "openai":
            if config.open_ai_chat_completion_models is not None:
                config.open_ai_chat_completion_models.add(key)
            elif hasattr(litellm, "open_ai_chat_completion_models"):
                litellm.open_ai_chat_completion_models.add(key)
                
        elif value.get("litellm_provider") == "anthropic":
            if config.anthropic_models is not None:
                config.anthropic_models.add(key)
            elif hasattr(litellm, "anthropic_models"):
                litellm.anthropic_models.add(key)
                
    return loaded_model_cost

def get_provider_for_model(model_name: str) -> str | None:
    model_info = model_cost.get(model_name, {})
    return model_info.get("litellm_provider")

def _update_dictionary(existing_dict: Dict, new_dict: dict) -> dict:
    for k, v in new_dict.items():
        if v is not None:
            if isinstance(v, str):
                existing_dict[k] = _convert_stringified_numbers(v)
            elif isinstance(v, dict):
                existing_nested_dict = existing_dict.get(k)
                if isinstance(existing_nested_dict, dict):
                    existing_nested_dict.update(v)
                    existing_dict[k] = existing_nested_dict
                else:
                    existing_dict[k] = v
            else:
                existing_dict[k] = v
    return existing_dict

def _convert_stringified_numbers(value):
    if isinstance(value, str):
        try:
            if "e" in value.lower() or "." in value:
                return float(value)
            else:
                return int(value)
        except (ValueError, TypeError):
            return value
    return value

def _clear_model_info_caches() -> None:
    """Clears LRU caches when model cost data is mutated."""
    try:
        from anchor.model.info.entry import _cached_get_model_info
        _cached_get_model_info.cache_clear()
    except ImportError:
        pass

## Global State Hijacking (Monkey Patch)
litellm.model_cost = model_cost
litellm.register_model = register_model

if hasattr(litellm, "utils"):
    litellm.utils.register_model = register_model
    litellm.utils._get_model_info_helper = _get_model_info_helper