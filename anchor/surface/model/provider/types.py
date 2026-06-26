# anchor.surface.model.provider.types
## @lineage: anchor.model.provider.types
from enum import Enum

class ProviderTypes(str, Enum):
    OPENAI = "openai"
    CHATGPT = "chatgpt"
    OPENAI_LIKE = "openai_like"
    ANTHROPIC = "anthropic"
    ANTHROPIC_TEXT = "anthropic_text"
    HUGGINGFACE = "huggingface"
    VERTEX_AI = "vertex_ai"
    GEMINI = "gemini"
    BEDROCK = "bedrock"
    OLLAMA = "ollama"
    PERPLEXITY = "perplexity"
    MISTRAL = "mistral"
    A2A = "a2a"
    DEEPSEEK = "deepseek"
    SAMBANOVA = "sambanova"
    DATABRICKS = "databricks"
    GITHUB = "github"
    CUSTOM = "custom"
    LITELLM_PROXY = "litellm_proxy"
    HOSTED_VLLM = "hosted_vllm"
    LM_STUDIO = "lm_studio"
    AIOHTTP_OPENAI = "aiohttp_openai"
    LANGFUSE = "langfuse"
    GITHUB_COPILOT = "github_copilot"
    SNOWFLAKE = "snowflake"
    LLAMA = "meta_llama"
    CURSOR = "cursor"

ProviderTypesSet = {provider.value for provider in ProviderTypes}