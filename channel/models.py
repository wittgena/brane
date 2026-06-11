# channel.models
## @lineage: channel.gov.models
## @lineage: gov.gateway.models
## @lineage: gov.gateway.service.models
from abc import ABC
from datetime import datetime
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field, field_validator
from gov.gate.llm.driver import Driver
from agent.llm.actor import Agent
from meta.watcher.tracker.conv.stats import ConversationStats
from gov.gate.io.resource.req.request import (  # re-export for backward compat
    ACPEnabledAgent as ACPEnabledAgent,
    SendMessageRequest as SendMessageRequest,
    StartACPConversationRequest as StartACPConversationRequest,
    StartConversationRequest as StartConversationRequest,
)
from meta.ops.observer.security.secret.registry import SecretRegistry
from agent.loop.conv.status import ConversationExecutionStatus
from gov.gate.call.types import ConversationTags
from agent.loop.event.base import Event
from meta.ops.observer.security.secret.source import SecretSource
from agent.manager.workspace.base import BaseWorkspace
from gov.gate.call.tool.message import (  # re-export
    ImageContent as ImageContent,
    TextContent as TextContent,
)
from meta.watcher.tracker.conv.metrics import MetricsSnapshot
from meta.ops.observer.security.base import SecurityAnalyzerBase
from meta.ops.observer.security.auth.confirm import (
    ConfirmationPolicyBase,
    NeverConfirm,
)
from arch.proto.event.next import ToposId, utc_now
from arch.topos.state.disc import DiscMixin
from arch.topos.state.surge import SurgeBaseModel
from arch.proto.event.next import next_id

class ServerErrorEvent(Event):
    code: str = Field(description="Code for the error - typically an error type")
    detail: str = Field(description="Details about the error")

class ConversationSortOrder(str, Enum):
    """Enum for conversation sorting options."""

    CREATED_AT = "CREATED_AT"
    UPDATED_AT = "UPDATED_AT"
    CREATED_AT_DESC = "CREATED_AT_DESC"
    UPDATED_AT_DESC = "UPDATED_AT_DESC"

class EventSortOrder(str, Enum):
    """Enum for event sorting options."""

    TIMESTAMP = "TIMESTAMP"
    TIMESTAMP_DESC = "TIMESTAMP_DESC"

class StoredConversation(StartACPConversationRequest):
    id: ToposId
    title: str | None = Field(
        default=None, description="User-defined title for the conversation"
    )
    metrics: MetricsSnapshot | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

class _ConversationInfoBase(SurgeBaseModel):
    """Common conversation info fields shared by conversation contracts."""

    id: ToposId = Field(description="Unique conversation ID")
    workspace: BaseWorkspace = Field(
        ...,
        description=(
            "Workspace used by the agent to execute commands and read/write files. "
            "Not the process working directory."
        ),
    )
    persistence_dir: str | None = Field(
        default="workspace/conversations",
        description="Directory for persisting conversation state and events. "
        "If None, conversation will not be persisted.",
    )
    max_iterations: int = Field(
        default=500,
        gt=0,
        description=(
            "Maximum number of iterations the agent can perform in a single run."
        ),
    )
    stuck_detection: bool = Field(
        default=True,
        description="Whether to enable stuck detection for the agent.",
    )
    execution_status: ConversationExecutionStatus = Field(
        default=ConversationExecutionStatus.IDLE
    )
    confirmation_policy: ConfirmationPolicyBase = Field(default=NeverConfirm())
    security_analyzer: SecurityAnalyzerBase | None = Field(
        default=None,
        description="Optional security analyzer to evaluate action risks.",
    )
    activated_knowledge_skills: list[str] = Field(
        default_factory=list,
        description="List of activated knowledge skills name",
    )
    blocked_actions: dict[str, str] = Field(
        default_factory=dict,
        description="Actions blocked by PreToolUse hooks, keyed by action ID",
    )
    blocked_messages: dict[str, str] = Field(
        default_factory=dict,
        description="Messages blocked by UserPromptSubmit hooks, keyed by message ID",
    )
    last_user_message_id: str | None = Field(
        default=None,
        description=(
            "Most recent user MessageEvent id for hook block checks. "
            "Updated when user messages are emitted so Agent.step can pop "
            "blocked_messages without scanning the event log. If None, "
            "hook-blocked checks are skipped (legacy conversations)."
        ),
    )
    stats: ConversationStats = Field(
        default_factory=ConversationStats,
        description="Conversation statistics for tracking LLM metrics",
    )
    secret_registry: SecretRegistry = Field(
        default_factory=SecretRegistry,
        description="Registry for handling secrets and sensitive data",
    )
    agent_state: dict[str, Any] = Field(
        default_factory=dict,
        description="Dictionary for agent-specific runtime state that persists across "
        "iterations.",
    )
    hook_config: Any = None 
    title: str | None = Field(
        default=None, description="User-defined title for the conversation"
    )
    metrics: MetricsSnapshot | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    tags: ConversationTags = Field(
        default_factory=dict,
        description=(
            "Key-value tags for the conversation. Keys must be lowercase "
            "alphanumeric. Values are arbitrary strings up to 256 characters."
        ),
    )

class ConversationInfo(_ConversationInfoBase):
    """Information about a conversation running locally without a Runtime sandbox."""

    agent: Agent = Field(
        ...,
        description=(
            "The legacy v1 agent configuration. "
            "This endpoint remains pinned to the standard Agent contract."
        ),
    )

class ConversationPage(SurgeBaseModel):
    items: list[ConversationInfo]
    next_page_id: str | None = None

class ACPConversationInfo(_ConversationInfoBase):
    """Conversation info that supports ACP-capable agent configs."""
    agent: ACPEnabledAgent = Field(
        ...,
        description=(
            "The agent running in the conversation. "
            "Supports both Agent and ACPAgent payloads."
        ),
    )


class ACPConversationPage(SurgeBaseModel):
    items: list[ACPConversationInfo]
    next_page_id: str | None = None

class ConversationResponse(SurgeBaseModel):
    conversation_id: str
    state: ConversationExecutionStatus

class ConfirmationResponseRequest(SurgeBaseModel):
    """Payload to accept or reject a pending action."""
    accept: bool
    reason: str = "User rejected the action."

class Success(SurgeBaseModel):
    success: bool = True

class EventPage(SurgeBaseModel):
    items: list[Event]
    next_page_id: str | None = None

class UpdateSecretsRequest(SurgeBaseModel):
    """Payload to update secrets in a conversation."""

    secrets: dict[str, SecretSource] = Field(
        description="Dictionary mapping secret keys to values"
    )

    @field_validator("secrets", mode="before")
    @classmethod
    def convert_string_secrets(cls, v: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(v, dict):
            return v

        converted = {}
        for key, value in v.items():
            if isinstance(value, str):
                # Convert plain string to StaticSecret dict format
                converted[key] = {
                    "kind": "StaticSecret",
                    "value": value,
                }
            elif isinstance(value, dict):
                if "value" in value and "kind" not in value:
                    # Convert dict with value field to StaticSecret dict format
                    converted[key] = {
                        "kind": "StaticSecret",
                        "value": value["value"],
                    }
                else:
                    # Keep existing SecretSource objects or properly formatted dicts
                    converted[key] = value
            else:
                # Keep other types as-is (will likely fail validation later)
                converted[key] = value

        return converted


class SetConfirmationPolicyRequest(SurgeBaseModel):
    """Payload to set confirmation policy for a conversation."""
    policy: ConfirmationPolicyBase = Field(description="The confirmation policy to set")

class SetSecurityAnalyzerRequest(SurgeBaseModel):
    "Payload to set security analyzer for a conversation"
    security_analyzer: SecurityAnalyzerBase | None = Field(
        description="The security analyzer to set"
    )

class UpdateConversationRequest(SurgeBaseModel):
    """Payload to update conversation metadata."""
    title: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="New conversation title",
    )
    tags: ConversationTags | None = Field(
        default=None,
        description=(
            "Key-value tags to set on the conversation. Keys must be lowercase "
            "alphanumeric. Values are arbitrary strings up to 256 characters. "
            "Replaces all existing tags when provided."
        ),
    )

class GenerateTitleRequest(SurgeBaseModel):
    """Payload to generate a title for a conversation."""
    max_length: int = Field(
        default=50, ge=1, le=200, description="Maximum length of the generated title"
    )
    llm: Driver | None = Field(
        default=None, description="Optional LLM to use for title generation"
    )

class GenerateTitleResponse(SurgeBaseModel):
    """Response containing the generated conversation title."""
    title: str = Field(description="The generated title for the conversation")

class AskAgentRequest(SurgeBaseModel):
    """Payload to ask the agent a simple question."""
    question: str = Field(description="The question to ask the agent")

class AskAgentResponse(SurgeBaseModel):
    """Response containing the agent's answer."""
    response: str = Field(description="The agent's response to the question")

class AgentResponseResult(SurgeBaseModel):
    response: str = Field(
        description=(
            "The agent's final response text. Extracted from either a "
            "FinishAction message or the last agent MessageEvent. "
            "Empty string if no final response is available."
        )
    )

class BashEventBase(DiscMixin, ABC):
    """Base class for all bash event types"""
    id: ToposId = Field(default_factory=next_id)
    timestamp: datetime = Field(default_factory=utc_now)

class ExecuteBashRequest(SurgeBaseModel):
    command: str = Field(description="The bash command to execute")
    cwd: str | None = Field(default=None, description="The current working directory")
    timeout: int = Field(
        default=300,
        description="The max number of seconds a command may be permitted to run.",
    )

class BashCommand(BashEventBase, ExecuteBashRequest):
    pass

class BashOutput(BashEventBase):
    command_id: ToposId
    order: int = Field(
        default=0, description="The order for this output, sequentially starting with 0"
    )
    exit_code: int | None = Field(
        default=None, description="Exit code None implies the command is still running."
    )
    stdout: str | None = Field(
        default=None, description="The standard output from the command"
    )
    stderr: str | None = Field(
        default=None, description="The error output from the command"
    )

class BashError(BashEventBase):
    code: str = Field(description="Code for the error - typically an error type")
    detail: str = Field(description="Details about the error")

class BashEventSortOrder(Enum):
    TIMESTAMP = "TIMESTAMP"
    TIMESTAMP_DESC = "TIMESTAMP_DESC"

class BashEventPage(SurgeBaseModel):
    items: list[BashEventBase]
    next_page_id: str | None = None
