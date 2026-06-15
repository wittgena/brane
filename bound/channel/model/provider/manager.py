# bound.channel.model.provider.manager
## @lineage: channel.model.provider.manager
from __future__ import annotations
from functools import lru_cache
from typing import Callable, Optional, Union

from anchor.config.resolver import config
from anchor.config.constants import DEFAULT_MAX_LRU_CACHE_SIZE
from bound.channel.model.types.provider import LlmProviders
from anchor.model import BaseLLMModelInfo
from bound.channel.model.types.utils import LlmProvidersSet, ProviderSpecificModelInfo

class ProviderConfigManager:
    _PROVIDER_CONFIG_MAP: Optional[dict[LlmProviders, tuple[Callable, bool]]] = None

    @staticmethod
    def _build_provider_config_map() -> dict[LlmProviders, tuple[Callable, bool]]:
        return {
            # Format: (factory_function, needs_model_parameter: bool)
            LlmProviders.OPENAI: (lambda: config.OpenAIGPTConfig(), False),
            LlmProviders.ANTHROPIC: (lambda: config.AnthropicConfig(), False),
            LlmProviders.A2A: (lambda: config.A2AConfig(), False),
            LlmProviders.LLAMA: (lambda: config.LlamaAPIConfig(), False),
            LlmProviders.CHATGPT: (lambda: config.ChatGPTConfig(), False),
            LlmProviders.CUSTOM: (lambda: config.OpenAILikeChatConfig(), False),
            LlmProviders.AIOHTTP_OPENAI: (lambda: config.AiohttpOpenAIChatConfig(), False),
            LlmProviders.HUGGINGFACE: (lambda: config.HuggingFaceChatConfig(), False),
            LlmProviders.GEMINI: (lambda: config.GoogleAIStudioGeminiConfig(), False),
            LlmProviders.OLLAMA: (lambda: config.OllamaConfig(), False)
        }

    @staticmethod
    def get_provider_chat_config(
        model: str,
        provider: LlmProviders,
        base_model: Optional[str] = None,
    ):
        if provider == LlmProviders.OPENAI:
            if config.openaiOSeriesConfig.is_model_o_series_model(model=model):
                return config.openaiOSeriesConfig
            if config.OpenAIGPT5Config.is_model_gpt_5_model(model=model):
                return config.OpenAIGPT5Config()

        # Initialize provider config map lazily to avoid circular imports
        if ProviderConfigManager._PROVIDER_CONFIG_MAP is None:
            ProviderConfigManager._PROVIDER_CONFIG_MAP = (
                ProviderConfigManager._build_provider_config_map()
            )

        config_entry = ProviderConfigManager._PROVIDER_CONFIG_MAP.get(provider)
        if config_entry is not None:
            config_factory, needs_model = config_entry
            if needs_model:
                return config_factory(model)
            else:
                return config_factory()
        return None

    @staticmethod
    def get_provider_anthropic_messages_config(
        model: str,
        provider: LlmProviders,
    ):
        return ProviderConfigManager._get_provider_anthropic_messages_config_cached(
            model=model, provider=provider
        )

    @staticmethod
    @lru_cache(maxsize=DEFAULT_MAX_LRU_CACHE_SIZE)
    def _get_provider_anthropic_messages_config_cached(
        model: str,
        provider: LlmProviders,
    ):
        if LlmProviders.ANTHROPIC == provider:
            return config.AnthropicMessagesConfig()
        return None

    @staticmethod
    def get_provider_audio_transcription_config(
        model: str,
        provider: LlmProviders,
    ):
        if LlmProviders.OPENAI == provider:
            if "gpt-4o" in model:
                return config.OpenAIGPTAudioTranscriptionConfig()
            else:
                return config.OpenAIWhisperAudioTranscriptionConfig()
        return None

    @staticmethod
    def get_provider_responses_api_config(
        provider: Union[LlmProviders, str],
        model: Optional[str] = None,
    ):
        provider_enum: Optional[LlmProviders] = None
        if isinstance(provider, LlmProviders):
            provider_enum = provider
        else:
            try:
                provider_enum = LlmProviders(provider)
            except ValueError:
                pass

        return ProviderConfigManager._get_python_responses_api_config(provider_enum, model)

    @staticmethod
    def _get_python_responses_api_config(
        provider: Optional[LlmProviders],
        model: Optional[str] = None,
    ):
        if provider is None:
            return None
        if LlmProviders.OPENAI == provider:
            return config.OpenAIResponsesAPIConfig()
        elif LlmProviders.CHATGPT == provider:
            return config.ChatGPTResponsesAPIConfig()
        return None

    @staticmethod
    def get_provider_skills_api_config(
        provider: LlmProviders,
    ):
        if LlmProviders.ANTHROPIC == provider:
            return config.AnthropicSkillsConfig()
        return None

    @staticmethod
    def get_provider_evals_api_config(
        provider: LlmProviders,
    ):
        # Migrated from direct import to resolver
        if LlmProviders.OPENAI == provider:
            return config.OpenAIEvalsConfig()
        return None

    @staticmethod
    def get_provider_model_info(
        model: Optional[str],
        provider: LlmProviders,
    ) -> Optional[BaseLLMModelInfo]:
        if LlmProviders.OPENAI == provider:
            return config.OpenAIGPTConfig()
        elif LlmProviders.GEMINI == provider:
            return config.GeminiModelInfo()
        elif LlmProviders.ANTHROPIC == provider:
            return config.AnthropicModelInfo()
        elif LlmProviders.OLLAMA == provider or LlmProviders.OLLAMA_CHAT == provider:
            # Migrated from direct import to resolver
            return config.OllamaModelInfo()
        return None

    @staticmethod
    def get_provider_vector_stores_config(
        provider: LlmProviders,
        api_type: Optional[str] = None,
    ):
        # Migrated from direct imports to resolver
        if LlmProviders.OPENAI == provider:
            return config.OpenAIVectorStoreConfig()
        elif LlmProviders.GEMINI == provider:
            return config.GeminiVectorStoreConfig()
        elif LlmProviders.S3_VECTORS == provider:
            return config.S3VectorsVectorStoreConfig()
        return None

    @staticmethod
    def get_provider_vector_store_files_config(
        provider: LlmProviders,
    ):
        # Migrated from direct import to resolver
        if LlmProviders.OPENAI == provider:
            return config.OpenAIVectorStoreFilesConfig()
        return None

    @staticmethod
    def get_provider_text_to_speech_config(
        model: str,
        provider: LlmProviders,
    ):
        return None

def get_provider_info(
    model: str, custom_llm_provider: Optional[str]
) -> Optional[ProviderSpecificModelInfo]:
    """Helper to fetch provider-specific model info dynamically."""
    provider_config: Optional[BaseLLMModelInfo] = None
    if custom_llm_provider and custom_llm_provider in LlmProvidersSet:
        provider_config = ProviderConfigManager.get_provider_model_info(
            model=model, provider=LlmProviders(custom_llm_provider)
        )

    model_info: Optional[ProviderSpecificModelInfo] = None
    if provider_config:
        model_info = provider_config.get_provider_info(model=model)
    return model_info