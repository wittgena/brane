# bound.router.adapter.llm
"""
@manifold: Hybrid Microkernel Router
@flow: Native Registry ⊕ Dynamic Scanner -> Unified Routing Table -> Lazy Instantiation
@desc: Orchestrates the coexistence of batteries-included LLM cores and dynamically transduced LlamaIndex modules.
"""
import importlib
import inspect
from typing import Dict, Any, Optional

from anchor.provider.cost.map import get_provider_for_model
from anchor.cli.adapter.scan.llm import LLMScanner
import anchor.inter.llms as llm_pkg 

from watcher.plane.emitter import get_emitter

log = get_emitter("llm.router")

_LLM_PKG_NAME = llm_pkg.__name__  ## @ex: "anchor.inter.llms"
_LLM_PKG_PATH = _LLM_PKG_NAME.replace(".", "/")  ## @ex: "anchor/inter/llms"

## @state: Core topological boundaries (Batteries-included)
DEFAULT_LLM_REGISTRY = {
    "openai": {
        "module": f"{_LLM_PKG_NAME}.openai.base",
        "class": "OpenAI",
        "tags": ["gpt-4", "gpt-3.5", "o1"],
        "is_native": True,
        "capabilities": {
            "is_function_calling": True,
            "is_openai_like": True,
            "is_multimodal": True,
            "supports_structured_outputs": True
        },
        "accepted_kwargs": [
            "model", "temperature", "max_tokens", "additional_kwargs", 
            "max_retries", "timeout", "api_key", "api_base", "system_prompt"
        ]
    },
    "anthropic": {
        "module": f"{_LLM_PKG_NAME}.anthropic.base",
        "class": "Anthropic",
        "tags": ["claude"],
        "is_native": True,
        "capabilities": {
            "is_function_calling": True,
            "is_openai_like": False,
            "is_multimodal": True,
            "supports_structured_outputs": True
        },
        "accepted_kwargs": [
            "model", "temperature", "max_tokens", "additional_kwargs", 
            "max_retries", "timeout", "api_key", "system_prompt"
        ]
    },
    "gemini": {
        "module": f"{_LLM_PKG_NAME}.google_genai.base",
        "class": "GoogleGenAI",
        "tags": ["gemini"],
        "is_native": True,
        "capabilities": {
            "is_function_calling": True,
            "is_openai_like": False,
            "is_multimodal": True,
            "supports_structured_outputs": True
        },
        "accepted_kwargs": [
            "model", "temperature", "max_tokens", "additional_kwargs", 
            "max_retries", "api_key", "system_prompt"
        ]
    }
}

class LLMRouter:
    def __init__(self, base_path: str = _LLM_PKG_PATH):
        self.scanner = LLMScanner(base_path=base_path)
        
        ## @bind: Initialize native registry (Deep copy to prevent structural contamination)
        self.registry = {k: v.copy() for k, v in DEFAULT_LLM_REGISTRY.items()}
        
        ## @merge: Absorb dynamic transduced modules (Allows hot-patching)
        self._merge_dynamic_registry()

    def _merge_dynamic_registry(self):
        log.debug("[Router] Scanning for dynamically trans-ed modules...")
        scanned_data = self.scanner.scan(target="local")
        
        dynamic_count = 0
        for provider, info in scanned_data.items():
            ## @shield: Prevent redundant mapping of intrinsic native modules
            if provider in self.registry and self.registry[provider].get("is_native"):
                ## @bypass: Skip unless intentionally hot-patched by user via trans.llama
                if _LLM_PKG_NAME in info["module"] and provider in DEFAULT_LLM_REGISTRY:
                    continue
            
            ## @inject: Map the discovered external topology & Absorb Rich Metadata
            self.registry[provider] = {
                "module": info["module"],
                "class": info["class"],
                "tags": info.get("tags", [provider]),
                "is_native": False,
                "capabilities": info.get("capabilities", {}),
                "accepted_kwargs": info.get("accepted_kwargs", [])
            }
            dynamic_count += 1
            
        log.info(f"[Router] Registry Ready: {len(DEFAULT_LLM_REGISTRY)} Native, {dynamic_count} Dynamic modules.")

    def _fallback_provider_match(self, model_name: str) -> Optional[str]:
        ## @infer: Derive provider identity via spatial tag resonance
        for provider, meta in self.registry.items():
            if provider in model_name:
                return provider
            if any(tag in model_name for tag in meta["tags"]):
                return provider
        return None

    def route_and_load(self, model_name: str, **kwargs) -> Any:
        ## @resolve: Identify target topology based on model signature
        provider = get_provider_for_model(model_name)
        if not provider:
            provider = self._fallback_provider_match(model_name)
            
        if not provider:
            raise ValueError(f"[Error] 모델 '{model_name}'에 대한 Provider를 식별할 수 없습니다.")

        meta = self.registry.get(provider)
        if not meta:
            ## @rupture: Explicit boundary error guiding the user to dynamic transduction
            raise ValueError(
                f"\n[Brane Integration Error] Module '{provider}' is missing from the manifold.\n"
                f"This topology is not natively embedded.\n"
                f"Dynamically transduce via CLI: `python -m trans.llama --category llms --name {provider}`"
            )

        module_path = meta["module"]
        try:
            ## @load: Lazy instantiation of the target module
            module = importlib.import_module(module_path)
        except ImportError as e:
            raise ImportError(f"[Router] Failed to materialize module '{module_path}': {e}")

        
        ## @extract: Isolate the core LLM execution class (우아한 동적 매핑 적용)
        LLMClass = None
        expected_class_name = meta.get("class")

        ## @find.step.1: 메타데이터에 명시된 클래스명이 실제로 존재하는지 확인
        if expected_class_name and hasattr(module, expected_class_name):
            LLMClass = getattr(module, expected_class_name)
        else:
            if expected_class_name:
                log.warning(f"[Router] 지정된 클래스 '{expected_class_name}'를 찾을 수 없습니다. 동적 클래스 추론을 시도합니다.")
            
            ## @find.step.2: 모듈 내부를 검사하여 LLM 역할을 하는 클래스를 스스로 찾아냄 (Duck Typing)
            for name, obj in inspect.getmembers(module, inspect.isclass):
                ## 다른 파일에서 import 된 Base 클래스들을 배제하고, 이 모듈에서 '직접 정의된' 클래스만 타겟팅
                if obj.__module__ == module.__name__:
                    ## LLM의 특징(이름이 LLM으로 끝나거나, chat/complete 메서드를 가짐)을 보유했는지 검사
                    if name.endswith("LLM") or hasattr(obj, 'chat') or hasattr(obj, 'complete'):
                        LLMClass = obj
                        log.info(f"[Router] 동적 추론 성공: '{name}' 클래스를 LLM 구현체로 바인딩합니다.")
                        break

        if not LLMClass:
            raise RuntimeError(f"[Router] '{module_path}' 내부에서 실행 가능한 LLM 클래스를 찾을 수 없습니다.")

        ## @bind: Instantiate and project the kwargs into the LlamaIndex boundary
        accepted_kwargs = meta.get("accepted_kwargs", [])
        if accepted_kwargs:
            valid_kwargs = {k: v for k, v in kwargs.items() if k in accepted_kwargs}
            dropped_kwargs = set(kwargs.keys()) - set(valid_kwargs.keys())
            
            if dropped_kwargs:
                log.warning(f"[Router] Filtered unsupported kwargs for {provider} ({model_name}): {dropped_kwargs}")
            
            return LLMClass(model=model_name, **valid_kwargs)
        return LLMClass(model=model_name, **kwargs)

    def get_llm_tool_schema(self) -> Dict[str, Any]:
        ## @schema: Expose router interface for recursive function calling capabilities
        return {
            "name": "llm_model_router",
            "description": "Dynamically instantiates and returns an LLM execution object based on model topology.",
            "available_providers": list(self.registry.keys())
        }