# anchor.model.provider.adapter.registry
"""
@manifold: Adapter Registry (Microkernel Core)
@flow: Provider Vector -> Lazy Instantiation -> Adapter Binding
@desc: 
- Anchors provider identities to their corresponding structural execution adapters
- Ensures singleton lazy-loading to prevent premature memory collapse
"""
from typing import Any, Dict, List, Optional, Union
from anchor.switch.params import ModelResponse
from anchor.surface.legacy.action.preprocessor import CompletionContext
from anchor.model.provider.adapter.inter import InterLLMAdapter
from anchor.model.provider.adapter.base import BaseProviderAdapter, OpenAICompatibleAdapter, GenericHTTPAdapter

from bound.channel.action.handler.completor import CompletionHandler
from bound.transport.stream.wrapper import CustomStreamWrapper
from bound.xor.secret.manager import get_secret_bool
from bound.inter.llms.openai.completion import OpenAIChatCompletion

from watcher.plane.emitter import get_emitter

log = get_emitter("adapter.registry")

class AdapterRegistry:
    """@state: Internal mapping boundaries and phase lock"""
    _adapters: Dict[str, BaseProviderAdapter] = {}
    _fallback_adapter: Optional[BaseProviderAdapter] = None
    _is_initialized: bool = False

    @classmethod
    def setup_defaults(cls):
        ## @phase: Initialize primary kernels (Lazy Load Boundary)
        if cls._is_initialized:
            return

        log.debug("[Registry] 시스템 코어 레지스트리 초기화 시작 (최초 1회 실행)")

        openai_adapter = OpenAICompatibleAdapter()
        generic_adapter = GenericHTTPAdapter()
        inter_adapter = InterLLMAdapter()

        cls._fallback_adapter = generic_adapter

        ## @bind: Map canonical OpenAI-compliant providers to the standard envelope
        for provider in ["openai", "custom_openai", "azure", "groq", "mistral", "anyscale", "deepinfra"]:
            cls.register(provider, openai_adapter)

        ## @bind: Map generic HTTP protocols to the fallback envelope
        for provider in ["ollama", "huggingface"]:
            cls.register(provider, generic_adapter)

        ## @bind: Map external/complex topologies to the Universal InterAdapter
        cls.register("inter", inter_adapter)
        cls.register("anthropic", inter_adapter) 

        ## @seal: Lock initialization state to prevent redundant allocation
        cls._is_initialized = True
        log.debug("[Registry] 시스템 코어 레지스트리 초기화 완료")

    @classmethod
    def register(cls, provider_name: str, adapter: BaseProviderAdapter):
        ## @mutate: Dynamically inject or overwrite a topological mapping at runtime
        cls._adapters[provider_name] = adapter
        log.debug(f"[Registry] '{provider_name}' 어댑터가 동적으로 등록/덮어쓰기 되었습니다.")

    @classmethod
    def get_adapter(cls, provider_name: str) -> BaseProviderAdapter:
        ## @resolve: Extract matching adapter, triggering initial ignition if dormant
        if not cls._is_initialized:
            cls.setup_defaults()
        return cls._adapters.get(provider_name, cls._fallback_adapter)
