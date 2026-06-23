# anchor.model.llm.types.custom_http
## @lineage: anchor.model.types.llms.custom_http
## @lineage: anchor.router.model.types.llms.custom_http
## @lineage: bound.router.model.types.llms.custom_http
## @lineage: bound.channel.model.types.llms.custom_http
## @lineage: channel.model.types.llms.custom_http
## @lineage: gate.model.types.llms.custom_http
## @lineage: gate.types.llms.custom_http
import ssl
from enum import Enum
from typing import Union

class httpxSpecialProvider(str, Enum):
    LoggingCallback = "logging_callback"
    GuardrailCallback = "guardrail_callback"
    Caching = "caching"
    Oauth2Check = "oauth2_check"
    Oauth2Register = "oauth2_register"
    SecretManager = "secret_manager"
    PassThroughEndpoint = "pass_through_endpoint"
    PromptFactory = "prompt_factory"
    SSO_HANDLER = "sso_handler"
    Search = "search"
    MCP = "mcp"
    RAG = "rag"
    A2AProvider = "a2a_provider"
    AgentHealthCheck = "agent_health_check"
    A2A = "a2a"
    PromptManagement = "prompt_management"
    UI = "ui"

VerifyTypes = Union[str, bool, ssl.SSLContext]