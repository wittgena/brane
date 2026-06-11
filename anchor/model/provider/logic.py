# anchor.model.provider.logic
## @lineage: channel.provider.logic
## @lineage: gate.model.provider.logic
## @lineage: gate.llms.provider.logic
import re
from typing import Optional, Tuple
from bound.config.resolver import config

_CLAUDE_PATTERN = re.compile(r"^claude-[a-z]+-\d+-\d+(?:-\d{8})?$", re.IGNORECASE)

def _matches_claude_model_pattern(model: str) -> bool:
    """
    Check if a model string matches the Claude model naming pattern.
    Matches patterns like:
    - claude-opus-4-7
    - claude-sonnet-4-6
    - claude-haiku-4-5
    - claude-opus-5-1-20270101 (with optional date suffix)
    """
    return _CLAUDE_PATTERN.match(model) is not None

def _is_non_openai_azure_model(model: str) -> bool:
    """Azure 엔드포인트로 들어오지만 실제로는 OpenAI 모델이 아닌 경우(Cohere, Mistral 등)를 판별"""
    try:
        model_name = model.split("/", 1)[1]
        cohere_models = config.cohere_chat_models or []
        mistral_models = config.mistral_chat_models or []
        
        if (
            model_name in cohere_models 
            or f"mistral/{model_name}" in mistral_models
        ):
            return True
    except Exception:
        return False
    return False

def handle_cohere_chat_model_custom_llm_provider(
    model: str, custom_llm_provider: Optional[str] = None
) -> Tuple[str, Optional[str]]:
    """유저가 cohere_chat 모델을 단순히 'cohere' 프로바이더로 명시했을 때, 올바른 프로바이더(cohere_chat)로 교정"""
    cohere_models = config.cohere_chat_models or []
    if custom_llm_provider:
        if custom_llm_provider == "cohere" and model in cohere_models:
            return model, "cohere_chat"

    if model and "/" in model:
        _custom_llm_provider, _model = model.split("/", 1)
        if (
            _custom_llm_provider == "cohere"
            and _model in cohere_models
        ):
            return _model, "cohere_chat"

    return model, custom_llm_provider

def handle_anthropic_text_model_custom_llm_provider(
    model: str, custom_llm_provider: Optional[str] = None
) -> Tuple[str, Optional[str]]:
    """구형 Anthropic Text Completion 모델(claude-2, claude-instant 등)을 anthropic_text 프로바이더로 교정"""
    is_text_model = "claude-2" in model or "claude-instant" in model
    if custom_llm_provider:
        if custom_llm_provider == "anthropic" and is_text_model:
            return model, "anthropic_text"

    if model and "/" in model:
        _custom_llm_provider, _model = model.split("/", 1)
        if (_custom_llm_provider == "anthropic" and ("claude-2" in _model or "claude-instant" in _model)):
            return _model, "anthropic_text"

    return model, custom_llm_provider