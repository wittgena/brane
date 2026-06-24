# xphi.trans.llm.router
## @lineage: xphi.flow.llm.router
"""
@manifold: Hybrid Microkernel Router
@flow: Native Registry ⊕ Dynamic Scanner -> Unified Routing Table -> Lazy Instantiation
@desc: Orchestrates the coexistence of batteries-included LLM cores and dynamically transduced LlamaIndex modules.
"""
import importlib
import inspect
from typing import Dict, Any, Optional
from anchor.model.info.cost.map import get_provider_for_model
from watcher.plane.emitter import get_emitter
from xphi.trans.llm.scanner import LLMScanner

log = get_emitter("llm.router")

## @state: Core topological boundaries (Batteries-included)
DEFAULT_LLM_REGISTRY = {
    "openai": {
        "module": "bound.inter.llms.openai.base",
        "class": "OpenAI",
        "tags": ["gpt-4", "gpt-3.5", "o1"],
        "is_native": True
    },
    "anthropic": {
        "module": "bound.inter.llms.anthropic.base",
        "class": "Anthropic",
        "tags": ["claude"],
        "is_native": True
    },
    "gemini": {
        "module": "bound.inter.llms.google_genai.base",
        "class": "Gemini",
        "tags": ["gemini"],
        "is_native": True
    }
}

class LLMRouter:
    def __init__(self, base_path: str = "bound/inter/llms"):
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
                if "bound.inter.llms" in info["module"] and provider in DEFAULT_LLM_REGISTRY:
                    continue
            
            ## @inject: Map the discovered external topology
            self.registry[provider] = {
                "module": info["module"],
                "class": info["class"],
                "tags": info.get("tags", [provider]),
                "is_native": False
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

        ## @extract: Isolate the core LLM execution class
        LLMClass = None
        if "class" in meta and meta["class"]:
            LLMClass = getattr(module, meta["class"])
        else:
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if name.endswith("LLM") or hasattr(obj, 'chat'):
                    LLMClass = obj
                    break

        if not LLMClass:
            raise RuntimeError(f"[Router] No valid executable LLM class found within '{module_path}'.")

        ## @bind: Instantiate and project the kwargs into the LlamaIndex boundary
        return LLMClass(model=model_name, **kwargs)

    def get_llm_tool_schema(self) -> Dict[str, Any]:
        ## @schema: Expose router interface for recursive function calling capabilities
        return {
            "name": "llm_model_router",
            "description": "Dynamically instantiates and returns an LLM execution object based on model topology.",
            "available_providers": list(self.registry.keys())
        }