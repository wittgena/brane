# channel.model.info.openai_params
## @lineage: channel.model.info.support
from typing import Optional, Literal, List, Dict
from bound.config.resolver import config
from channel.model.provider.resolver import get_llm_provider
from channel.model.provider.manager import ProviderConfigManager
from anchor.base.exceptions import BadRequestError
from channel.model.types.utils import LlmProviders, LlmProvidersSet

from watcher.plane.emitter import get_emitter

log = get_emitter("info.openai_params")

def get_supported_openai_params(
    model: str,
    custom_llm_provider: Optional[str] = None,
    request_type: Literal[
        "chat_completion", "embeddings", "transcription"
    ] = "chat_completion",
    base_model: Optional[str] = None,
) -> Optional[list]:
    if not custom_llm_provider:
        try:
            custom_llm_provider = get_llm_provider(model=model)[1]
        except BadRequestError:
            return None

    if custom_llm_provider in LlmProvidersSet:
        provider_config = ProviderConfigManager.get_provider_chat_config(
            model=model,
            provider=LlmProviders(custom_llm_provider),
            base_model=base_model,
        )
    elif custom_llm_provider.split("/")[0] in LlmProvidersSet:
        provider_config = ProviderConfigManager.get_provider_chat_config(
            model=model,
            provider=LlmProviders(custom_llm_provider.split("/")[0]),
            base_model=base_model,
        )
    else:
        provider_config = None

    if provider_config and request_type == "chat_completion":
        supported_params = provider_config.get_supported_openai_params(model=model)
        if base_model and base_model != model:
            base_model_params = provider_config.get_supported_openai_params(
                model=base_model
            )
            supported_params = list(
                dict.fromkeys([*supported_params, *base_model_params])
            )
        return supported_params

    if custom_llm_provider == "ollama":
        return config.OllamaConfig().get_supported_openai_params(model=model)
    elif custom_llm_provider == "anthropic":
        return config.AnthropicConfig().get_supported_openai_params(model=model)
    elif custom_llm_provider == "openai":
        if request_type == "transcription":
            transcription_provider_config = (
                ProviderConfigManager.get_provider_audio_transcription_config(
                    model=model, provider=LlmProviders.OPENAI
                )
            )
            if isinstance(transcription_provider_config, config.OpenAIGPTAudioTranscriptionConfig):
                return transcription_provider_config.get_supported_openai_params(
                    model=model
                )
            else:
                raise ValueError(
                    f"Unsupported provider config: {transcription_provider_config} for model: {model}"
                )
        return config.OpenAIConfig().get_supported_openai_params(model=model)
    elif custom_llm_provider == "huggingface":
        return litellm.HuggingFaceChatConfig().get_supported_openai_params(model=model)
    return None
