# channel.model.cost.map
## @lineage: channel.cost.map
import os
import litellm # bridge.foming
from typing import Union, cast
from channel.model.provider.parser import get_model_cost_map
from channel.model.types.provider import LlmProviders
from bound.config.resolver import config
from channel.model.provider.gate import _update_dictionary, _invalidate_model_cost_lowercase_map
from channel.model.info.entry import get_model_info
from watcher.plane.emitter import get_emitter

log = get_emitter("bound.cost.model")

## Data Layer: 자체 비용 맵 초기화 (단일 진실 공급원 - SSOT)
model_cost_map_url: str = os.getenv(
    "LITELLM_MODEL_COST_MAP_URL",
    "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json",
)

## Gate 주도하에 메모리에 비용 데이터 로드
# [변경점 2] 파서가 (data, metadata) 튜플을 반환하므로, 첫 번째 값(데이터)만 취함
model_cost, _ = get_model_cost_map(url=model_cost_map_url)

## Mutation Layer: 독립적인 register_model 구현
def register_model(new_model_cost: Union[str, dict]):
    """
    동적으로 새로운 모델의 비용 및 메타데이터를 등록
    litellm의 전역 상태가 아닌, 현재 모듈의 model_cost를 직접 업데이트
    """
    loaded_model_cost = {}
    if isinstance(new_model_cost, dict):
        loaded_model_cost = new_model_cost
    elif isinstance(new_model_cost, str):
        # [변경점 3] 동적 로드 시에도 튜플 반환값 처리
        loaded_model_cost, _ = get_model_cost_map(url=new_model_cost)

    _skip_get_model_info_providers = {
        LlmProviders.GITHUB_COPILOT.value,
        LlmProviders.CHATGPT.value,
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
            
        ## override / add new keys to the existing model cost dictionary
        updated_dictionary = _update_dictionary(existing_model, value)
        model_cost.setdefault(model_cost_key, {}).update(updated_dictionary)
        _invalidate_model_cost_lowercase_map()

        log.debug(f"added/updated model={model_cost_key} in gate.bound.cost.model")
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
    """메모리에 로드된 model_cost 맵을 참조하여 해당 모델의 litellm_provider를 반환"""
    model_info = model_cost.get(model_name, {})
    return model_info.get("litellm_provider")


## Wiring Layer: 전역 상태 하이재킹 (과도기적 몽키 패치)
## [A] 데이터 참조(Memory Address) 병합 - litellm 내부에서 비용맵을 읽거나 쓸 때, 사실상 위에서 만든 Gate의 model_cost를 읽고 쓰게 됩니다.
litellm.model_cost = model_cost

## [B] 함수 포인터 교체 (Override) - litellm 내부의 Lazy Import 등으로 인해 발생하는 호출을 이 스크립트의 함수로 강제 라우팅합니다.
litellm.register_model = register_model

## (안전망) 만약 litellm 내부에서 `litellm.utils.register_model` 형태로 직접 접근하는 로직이 있다면 그것도 차단
if hasattr(litellm, "utils"):
    litellm.utils.register_model = register_model