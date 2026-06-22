# anchor.model.router.llm
## @lineage: bound.proxy.router.llm
## @lineage: anchor.router.llm
## @lineage: bound.router.llm
## @lineage: bound.channel.router.llm
import importlib
import inspect
from typing import Dict, Any, Optional

# 기존 cost.map 모듈에서 Provider 식별 함수를 가져옵니다.
from anchor.model.info.cost.map import get_provider_for_model

# Provider별 LLM 구현체가 위치할 기본 경로 매핑 (예시)
DEFAULT_LLM_REGISTRY = {
    "openai": {
        "module": "brane.channel.llama.llms.openai.base",
        "tags": ["gpt-4", "gpt-3.5", "dall-e"]
    },
    "anthropic": {
        "module": "brane.channel.llama.llms.anthropic.base",
        "tags": ["claude"]
    },
    "bedrock": {
        "module": "brane.channel.llama.llms.bedrock.base",
        "tags": ["nova", "stable-diffusion"]
    }
}

class LLMRouter:
    def __init__(self):
        # 클래스 레벨의 오염을 막기 위해 딥카피 형태로 사용
        self.registry = {k: v.copy() for k, v in DEFAULT_LLM_REGISTRY.items()}

    def _fallback_provider_match(self, model_name: str) -> Optional[str]:
        """
        cost.map에서 정확한 provider를 찾지 못했을 경우, 
        model_name에 포함된 키워드(태그)를 기반으로 유추합니다.
        """
        for provider, meta in self.registry.items():
            if provider in model_name:
                return provider
            if any(tag in model_name for tag in meta["tags"]):
                return provider
        return None

    def route_and_load(self, model_name: str, **kwargs) -> Any:
        """
        요청된 모델명에 맞춰 Provider를 식별하고, 해당 모듈을 지연 로드하여 LLM 인스턴스를 반환합니다.
        """
        # 1. Cost Map을 통해 Provider 식별 (단일 진실 공급원 활용)
        provider = get_provider_for_model(model_name)
        
        # 2. 식별 실패 시 Fallback 탐색
        if not provider:
            provider = self._fallback_provider_match(model_name)
            
        if not provider:
            raise ValueError(f"[Error] 모델 '{model_name}'에 대한 Provider를 식별할 수 없습니다.")

        # 3. 레지스트리에서 Provider 모듈 확인
        meta = self.registry.get(provider)
        if not meta:
            raise ValueError(f"[Error] 식별된 Provider '{provider}'에 대한 모듈 매핑이 없습니다.")

        module_path = meta["module"]

        # 4. 최소 의존성 지연 로드 (Lazy Load)
        try:
            module = importlib.import_module(module_path)
        except ImportError as e:
            raise ImportError(f"[Error] '{module_path}' 모듈을 로드할 수 없습니다. 패키지가 설치되어 있는지 확인하세요. ({e})")

        # 5. 클래스 동적 식별 (DataRouter의 inspect 패턴 재사용)
        LLMClass = None
        if "class" in meta:
            LLMClass = getattr(module, meta["class"])
        else:
            # 관례상 LLM의 초기화나 invoke 관련 메서드를 가진 클래스를 찾음
            for name, obj in inspect.getmembers(module, inspect.isclass):
                # 예: BaseLLM을 상속받았거나 특정 규약을 따르는 클래스 식별
                if name.endswith("LLM") or hasattr(obj, 'invoke'):
                    LLMClass = obj
                    break

        if not LLMClass:
            raise RuntimeError(f"'{module_path}' 내에 적합한 LLM 클래스가 없습니다.")

        # 6. 인스턴스화 및 반환 (kwargs로 api_key, temperature 등 전달)
        return LLMClass(model_name=model_name, **kwargs)

    def get_llm_tool_schema(self) -> Dict[str, Any]:
        """LLM Function Calling에 주입할 Tool Schema (필요시)"""
        return {
            "name": "llm_model_router",
            "description": "모델명을 입력받아 적합한 LLM 인스턴스를 생성하고 반환합니다.",
            "available_providers": list(self.registry.keys())
        }

if __name__ == "__main__":
    router = LLMRouter()
    
    # [시나리오 1] litellm cost map에 등록된 정상 모델 호출
    # "1024-x-1024/50-steps/bedrock/amazon.nova-canvas-v1:0" 은 provider가 "bedrock"으로 매핑됨
    test_model = "1024-x-1024/50-steps/bedrock/amazon.nova-canvas-v1:0"
    
    try:
        # 실제 환경에서는 bedrock 모듈이 로드되어 인스턴스를 반환합니다.
        llm_instance = router.route_and_load(test_model, temperature=0.7)
        print(f"Loaded instance for {test_model}")
    except Exception as e:
        print(f"Result: {e}")

    # [시나리오 2] fallback 작동 확인
    try:
        # cost map에 없어도 이름에 "gpt-4"가 들어가면 openai로 Fallback 유추
        llm_instance_2 = router.route_and_load("my-custom-gpt-4-model", max_tokens=1000)
    except Exception as e:
        print(f"Result: {e}")