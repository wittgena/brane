# channel.resource.req.request
## @lineage: gov.gateway.io.resource.req.request
## @lineage: gov.medium.io.resource.req.request
## @lineage: gov.io.resource.req.request
## @lineage: bound.io.resource.req.request
from __future__ import annotations
from typing import Annotated, Literal
from pydantic import BaseModel, Discriminator, Field, Tag, model_validator
from channel.acps import ACPAgent
from agent.llm.actor import Agent
from agent.call.types import ConversationTags
from gov.sandbox.field.hooks import HookConfig
from agent.call.tool.message import ImageContent, Message, TextContent
from gov.sandbox.field.plugin import PluginSource
from meta.ops.observer.security.secret.source import SecretSource
from meta.ops.observer.security.base import SecurityAnalyzerBase
from meta.ops.observer.security.auth.confirm import ConfirmationPolicyBase, NeverConfirm
from agent.llm.memory.codon.schema import AgentDefinition
from arch.topos.state.disc import kind_of
from agent.manager.workspace.local import LocalWorkspace
from arch.topos.state.surge import SurgeBaseModel
from watcher.plane.emitter import DEBUG, get_emitter

log = get_emitter(
    name="io.request", 
    phase="inter.space",
    boundary="bridge.io"
)

ACPEnabledAgent = Annotated[
    Annotated[Agent, Tag("Agent")] | Annotated[ACPAgent, Tag("ACPAgent")],
    Discriminator(kind_of),
]

class SendMessageRequest(SurgeBaseModel):
    """Payload to send a message to the agent."""

    role: Literal["user", "system", "assistant", "tool"] = "user"
    content: list[TextContent | ImageContent] = Field(default_factory=list)
    run: bool = Field(
        default=False,
        description="Whether the agent loop should automatically run if not running",
    )

    def create_message(self) -> Message:
        msg = Message(role=self.role, content=self.content)
        log.trace(
            "Created message from request", 
            role=self.role, 
            content_length=len(self.content),
            run_trigger=self.run
        )
        return msg

class _StartConversationRequestBase(SurgeBaseModel):
    """Common conversation creation fields shared by conversation contracts."""

    workspace: LocalWorkspace = Field(
        ...,
        description="Working directory for agent operations and tool execution",
    )
    conversation_id: ToposId | None = Field(
        default=None,
        description=("Optional conversation ID",),
    )
    confirmation_policy: ConfirmationPolicyBase = Field(
        default=NeverConfirm(),
        description="Controls when the conversation will prompt the user before "
        "continuing. Defaults to never.",
    )
    security_analyzer: SecurityAnalyzerBase | None = Field(
        default=None,
        description="Optional security analyzer to evaluate action risks.",
    )
    initial_message: SendMessageRequest | None = Field(
        default=None, description="Initial message to pass to the LLM"
    )
    max_iterations: int = Field(
        default=500,
        ge=1,
        description="If set, the max number of iterations the agent will run "
        "before stopping. This is useful to prevent infinite loops.",
    )
    stuck_detection: bool = Field(
        default=True,
        description="If true, the conversation will use stuck detection to "
        "prevent infinite loops.",
    )
    secrets: dict[str, SecretSource] = Field(
        default_factory=dict,
        description="Secrets available in the conversation",
    )
    tool_module_qualnames: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Mapping of tool names to their module qualnames from the client's "
            "registry. These modules will be dynamically imported on the server "
            "to register the tools for this conversation."
        ),
    )
    agent_definitions: list[AgentDefinition] = Field(
        default_factory=list,
        description=(
            "Agent definitions from the client's registry. These are "
            "registered on the server so that DelegateTool and TaskSetTool "
            "can see user-registered subagents."
        ),
    )
    plugins: list[PluginSource] | None = Field(
        default=None,
        description=(
            "List of plugins to load for this conversation. Plugins are loaded "
            "and their skills/MCP config are merged into the agent. "
            "Hooks are extracted and stored for runtime execution."
        ),
    )
    hook_config: HookConfig | None = Field(
        default=None,
        description=(
            "Optional hook configuration for this conversation. Hooks are shell "
            "scripts that run at key lifecycle events (PreToolUse, PostToolUse, "
            "UserPromptSubmit, Stop, etc.). If both hook_config and plugins are "
            "provided, they are merged with explicit hooks running before plugin "
            "hooks."
        ),
    )
    tags: ConversationTags = Field(
        default_factory=dict,
        description=(
            "Key-value tags for the conversation. Keys must be lowercase "
            "alphanumeric. Values are arbitrary strings up to 256 characters."
        ),
    )
    autotitle: bool = Field(
        default=True,
        description=(
            "If true, automatically generate a title for the conversation from "
            "the first user message using the conversation's LLM."
        ),
    )

    @model_validator(mode="after")
    def _log_request_initialization(self) -> "_StartConversationRequestBase":
        ## 메타데이터를 kwargs로 넘겨 SurfaceEmitter의 unified_context에 병합
        # log.debug(
        #     "Conversation request payload validated",
        #     conversation_id=str(self.conversation_id) if self.conversation_id else "auto-generated",
        #     workspace_path=str(self.workspace),
        #     agent_count=len(self.agent_definitions),
        #     plugin_count=len(self.plugins) if self.plugins else 0,
        #     has_hook_config=bool(self.hook_config),
        #     stuck_detection=self.stuck_detection
        # )
        return self


class StartConversationRequest(_StartConversationRequestBase):
    """Payload to create a new conversation"""
    agent: Agent


class StartACPConversationRequest(_StartConversationRequestBase):
    """Payload to create a conversation with ACP-capable agent support"""
    agent: ACPEnabledAgent
