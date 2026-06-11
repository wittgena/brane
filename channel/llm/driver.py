# channel.llm.driver
## @lineage: agent.llm.driver
from __future__ import annotations
import copy
import json
import os
import warnings
from collections.abc import Callable, Sequence
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, ClassVar, Literal, get_args, get_origin, Final, cast
import httpx
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    SecretStr,
    field_serializer,
    field_validator,
    model_validator,
)
from pydantic.json_schema import SkipJsonSchema
from agent.call.fallback import FallbackStrategy
from agent.manager.option.metadata import SettingProminence, field_meta
from meta.xor.manifold.block.residue import warn_deprecated
from meta.ops.observer.security.secret.manager import serialize_secret, validate_secret
from agent.call.tool.redef import ToolDefinition
from meta.ops.observer.security.auth.openai import transform_for_subscription
from channel.bound.config.resolver import config

from channel.bound.handler.stream.wrapper import CustomStreamWrapper

from channel.bound.completion import completion as litellm_completion
from channel.bound.handler.chunk.builder import stream_chunk_builder
from channel.bound.handler.response.main import responses as litellm_responses
from channel.switch.params import ModelResponse
from channel.bound.token.tokenizer import create_pretrained_tokenizer
from gate.model.support import supports_vision
from channel.bound.token.counter import token_counter
from agent.call.exceptions.types import LLMContextWindowTooSmallError
from agent.call.exceptions.mapping import map_provider_exception
from channel.llm.response import LLMResponse
from agent.call.tool.message import Message
from agent.call.mock import MockToolCallMixin
from agent.call.types import TokenCallbackType
from meta.watcher.tracker.conv.metrics import Metrics
from agent.call.info.model.features import get_features
from agent.llm.retry import RetryMixin
from channel.cost.telemetry import Telemetry
from channel.driver import DriverIO
from channel.llm.factory.driver import DriverFactory
from phase.bind.resolver import find_current_self
from watcher.plane.emitter import get_emitter

SELF_ROOT = find_current_self()
log = get_emitter(__name__)

MIN_CONTEXT_WINDOW_TOKENS: Final[int] = 16384
ENV_ALLOW_SHORT_CONTEXT_WINDOWS: Final[str] = "ALLOW_SHORT_CONTEXT_WINDOWS"
DEFAULT_MAX_OUTPUT_TOKENS_CAP: Final[int] = 16384

class Driver(BaseModel, RetryMixin, MockToolCallMixin):
    model: str = Field(
        default="claude-sonnet-4-20250514",
        description="Model name.",
        json_schema_extra=field_meta(SettingProminence.CRITICAL),
    )
    api_key: str | SecretStr | None = Field(
        default=None,
        description="API key.",
        json_schema_extra=field_meta(
            SettingProminence.CRITICAL,
            label="API Key",
        ),
    )
    base_url: str | None = Field(
        default=None,
        description="Custom base URL.",
        json_schema_extra=field_meta(SettingProminence.CRITICAL),
    )
    api_version: str | None = Field(default=None, description="API version (e.g., Azure).")
    aws_access_key_id: str | SecretStr | None = Field(default=None,)
    aws_secret_access_key: str | SecretStr | None = Field(default=None,)
    aws_session_token: str | SecretStr | None = Field(default=None,)
    aws_region_name: str | None = Field(default=None,)
    aws_profile_name: str | None = Field(default=None,)
    aws_role_name: str | None = Field(default=None,)
    aws_session_name: str | None = Field(default=None,)
    aws_bedrock_runtime_endpoint: str | None = Field(default=None,)

    openrouter_site_url: str = Field(default="https://localhost/",)
    openrouter_app_name: str = Field(default="surgent",)
    num_retries: int = Field(default=5, ge=0)
    retry_multiplier: float = Field(default=8.0, ge=0)
    retry_min_wait: int = Field(default=8, ge=0)
    retry_max_wait: int = Field(default=64, ge=0)
    timeout: int | None = Field(
        default=300,
        ge=0,
        description="HTTP timeout in seconds. Default is 300s (5 minutes). "
        "Set to None to disable timeout (not recommended for production).",
    )

    max_message_chars: int = Field(
        default=30_000,
        ge=1,
        description="Approx max chars in each event/content sent to the LLM.",
    )

    temperature: float | None = Field(
        default=None,
        ge=0,
        description=(
            "Sampling temperature for response generation. "
            "Defaults to None (uses provider default temperature). "
            "Set to 0.0 for deterministic outputs, "
            "or higher values (0.7-1.0) for more creative responses."
        ),
    )
    top_p: float | None = Field(
        default=None, ge=0, le=1,
        description=(
            "Nucleus sampling parameter. "
            "Defaults to None (uses provider default). "
            "Set to a value between 0 and 1 to control diversity of outputs."
        ),
    )
    top_k: float | None = Field(default=None, ge=0)
    max_input_tokens: int | None = Field(
        default=None, ge=1,
        description="The maximum number of input tokens. "
        "Note that this is currently unused, and the value at runtime is actually"
        " the total tokens in OpenAI (e.g. 128,000 tokens for GPT-4).",
    )
    max_output_tokens: int | None = Field(default=None, ge=1, description="The maximum number of output tokens. This is sent to the LLM.")
    model_canonical_name: str | None = Field(
        default=None,
        description=(
            "Optional canonical model name for feature registry lookups. "
            "maps model names to capabilities (e.g., vision support, "
            "prompt caching, responses API support). When using proxied or "
            "aliased model identifiers, set this field to the canonical "
            "model name (e.g., 'openai/gpt-4o') to ensure correct "
            "capability detection. If not provided, the 'model' field "
            "will be used for capability lookups."
        ),
    )
    extra_headers: dict[str, str] | None = Field(default=None, description="Optional HTTP headers to forward to LiteLLM requests.")
    input_cost_per_token: float | None = Field(default=None, ge=0, description="The cost per input token. This will available in logs for user.")
    output_cost_per_token: float | None = Field(default=None, ge=0, description="The cost per output token. This will available in logs for user.")
    ollama_base_url: str | None = Field(default=None,)
    stream: bool = Field(
        default=False,
        description=(
            "Enable streaming responses from the LLM. "
            "When enabled, the provided `on_token` callback in .completions "
            "and .responses will be invoked for each chunk of tokens."
        ),
    )
    drop_params: bool = Field(default=True)
    modify_params: bool = Field(
        default=True,
        description="Modify params allows litellm to do transformations like adding"
        " a default message, when a message is empty.",
    )
    disable_vision: bool | None = Field(
        default=None,
        description="If model is vision capable, this option allows to disable image "
        "processing (useful for cost reduction).",
    )
    disable_stop_word: bool | None = Field(default=False, description="Disable using of stop word.",)
    caching_prompt: bool = Field(
        default=True,
        description="Enable caching of prompts.",
    )
    log_completions: bool = Field(
        default=False,
        description="Enable logging of completions.",
    )
    log_completions_folder: str = Field(
        default=str(SELF_ROOT / "completions"),
        description="The folder to log LLM completions to. "
        "Required if log_completions is True.",
    )
    custom_tokenizer: str | None = Field(default=None, description="A custom tokenizer to use for token counting.",)
    native_tool_calling: bool = Field(default=True, description="Whether to use native tool calling.",)
    force_string_serializer: bool | None = Field(
        default=None,
        description=(
            "Force using string content serializer when sending to LLM API. "
            "If None (default), auto-detect based on model. "
            "Useful for providers that do not support list content, "
            "like HuggingFace and Groq."
        ),
    )
    reasoning_effort: Literal["low", "medium", "high", "xhigh", "none"] | None = Field(
        default="high",
        description="The effort to put into reasoning. "
        "This is a string that can be one of 'low', 'medium', 'high', 'xhigh', "
        "or 'none'. "
        "Can apply to all reasoning models.",
    )
    reasoning_summary: Literal["auto", "concise", "detailed"] | None = Field(
        default=None,
        description="The level of detail for reasoning summaries. "
        "This is a string that can be one of 'auto', 'concise', or 'detailed'. "
        "Requires verified OpenAI organization. Only sent when explicitly set.",
    )
    enable_encrypted_reasoning: bool = Field(
        default=True,
        description="If True, ask for ['reasoning.encrypted_content'] "
        "in Responses API include.",
    )
    # Prompt cache retention is filtered per model features in chat options.
    prompt_cache_retention: str | None = Field(
        default="24h",
        description=(
            "Retention policy for prompt cache. Only sent for supported models "
            "(GPT-5+ and GPT-4.1, excluding Azure deployments); explicitly "
            "stripped for all others."
        ),
    )
    extended_thinking_budget: int | None = Field(
        default=200_000,
        description="The budget tokens for extended thinking, "
        "supported by Anthropic models.",
    )
    seed: int | None = Field(default=None, description="The seed to use for random number generation.",)
    safety_settings: list[dict[str, str]] | None = Field(
        default=None,
        deprecated=("Deprecated since v1.15.0 and scheduled for removal in v1.20.0."),
        description=(
            "No-op. Safety settings are no longer applied. "
            "Deprecated since v1.15.0 and scheduled for removal in v1.20.0."
        ),
    )
    usage_id: str = Field(
        default="default",
        serialization_alias="usage_id",
        description=(
            "Unique usage identifier for the LLM. Used for registry lookups, "
            "telemetry, and spend tracking."
        ),
    )
    litellm_extra_body: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Additional key-value pairs to pass to litellm's extra_body parameter. "
            "This is useful for custom inference endpoints that need additional "
            "parameters for configuration, routing, or advanced features. "
            "NOTE: Not all LLM providers support extra_body parameters. Some providers "
            "(e.g., OpenAI) may reject requests with unrecognized options. "
            "This is commonly supported by: "
            "- LiteLLM proxy servers (routing metadata, tracing) "
            "- vLLM endpoints (return_token_ids, etc.) "
            "- Custom inference clusters "
            "Examples: "
            "- Proxy routing: {'trace_version': '1.0.0', 'tags': ['agent:my-agent']} "
            "- vLLM features: {'return_token_ids': True}"
        ),
    )

    fallback_strategy: FallbackStrategy | None = Field(
        default=None,
        description=(
            "Optional fallback strategy for trying alternate LLMs on transient "
            "failure. Construct with FallbackStrategy(fallback_llms=[...])."
            "Excluded from serialization; must be reconfigured after load."
        ),
        exclude=True,
    )

    ## I/O Controller (Hardware Interface)
    _io: DriverIO | None = PrivateAttr(default=None)

    ## Internal fields (excluded from dumps)
    retry_listener: SkipJsonSchema[
        Callable[[int, int, BaseException | None], None] | None
    ] = Field(default=None, exclude=True,)
    _metrics: Metrics | None = PrivateAttr(default=None)

    ## Runtime-only private attrs
    _model_info: Any = PrivateAttr(default=None)
    _tokenizer: Any = PrivateAttr(default=None)
    _telemetry: Telemetry | None = PrivateAttr(default=None)
    _is_subscription: bool = PrivateAttr(default=False)
    _litellm_provider: str | None = PrivateAttr(default=None)

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", arbitrary_types_allowed=True)

    ## Validators
    @field_validator("safety_settings", mode="before")
    @classmethod
    def _warn_safety_settings_deprecated(cls, v: list[dict[str, str]] | None) -> list[dict[str, str]] | None:
        if v is not None:
            warn_deprecated(
                "LLM.safety_settings",
                deprecated_in="1.15.0",
                removed_in="1.20.0",
                details="Safety settings are no longer applied.",
            )
        return v

    @field_validator("api_key", "aws_access_key_id", "aws_secret_access_key", "aws_session_token")
    @classmethod
    def _validate_secrets(cls, v: str | SecretStr | None, info) -> SecretStr | None:
        return validate_secret(v, info)

    @model_validator(mode="before")
    @classmethod
    def _coerce_inputs(cls, data):
        if not isinstance(data, dict):
            return data
        d = dict(data)

        model_val = d.get("model")
        if not model_val:
            raise ValueError("model must be specified in LLM")

        # Azure default version
        if model_val.startswith("azure") and not d.get("api_version"):
            d["api_version"] = "2024-12-01-preview"

        # Provider rewrite: surgent/* -> litellm_proxy/*
        if model_val.startswith("surgent/"):
            model_name = model_val.removeprefix("surgent/")
            d["model"] = f"litellm_proxy/{model_name}"
            # Set base_url (default to the app proxy when base_url is unset or None)
            # Use `or` instead of dict.get() to handle explicit None values
            d["base_url"] = d.get("base_url") or "https://llm-proxy.app.all-hands.dev/"

        return d

    @model_validator(mode="after")
    def _init_driver_subsystems(self):
        if self.openrouter_site_url:
            os.environ["OR_SITE_URL"] = self.openrouter_site_url
        if self.openrouter_app_name:
            os.environ["OR_APP_NAME"] = self.openrouter_app_name
        if self.aws_access_key_id:
            assert isinstance(self.aws_access_key_id, SecretStr)
            os.environ["AWS_ACCESS_KEY_ID"] = self.aws_access_key_id.get_secret_value()
        if self.aws_secret_access_key:
            assert isinstance(self.aws_secret_access_key, SecretStr)
            os.environ["AWS_SECRET_ACCESS_KEY"] = (
                self.aws_secret_access_key.get_secret_value()
            )
        if self.aws_session_token:
            assert isinstance(self.aws_session_token, SecretStr)
            os.environ["AWS_SESSION_TOKEN"] = self.aws_session_token.get_secret_value()
        if self.aws_region_name:
            os.environ["AWS_REGION_NAME"] = self.aws_region_name

        # Metrics + Telemetry wiring
        if self._metrics is None:
            self._metrics = Metrics(model_name=self.model)

        self._telemetry = Telemetry(
            model_name=self.model,
            log_enabled=self.log_completions,
            log_dir=self.log_completions_folder if self.log_completions else None,
            input_cost_per_token=self.input_cost_per_token,
            output_cost_per_token=self.output_cost_per_token,
            metrics=self._metrics,
        )

        ## Tokenizer
        if self.custom_tokenizer:
            self._tokenizer = create_pretrained_tokenizer(self.custom_tokenizer)

        ## Capabilities + model info
        # self._init_model_info_and_caps()
        # log.debug(
        #     f"LLM ready: model={self.model} base_url={self.base_url} "
        #     f"reasoning_effort={self.reasoning_effort} "
        #     f"temperature={self.temperature}"
        # )

        if self._io is None:
            self._io = DriverIO(driver=self)
        return self

    def _aws_kwargs(self) -> dict[str, str]:
        """Build kwargs dict for AWS params to pass to litellm calls."""
        kw: dict[str, str] = {}
        if self.aws_access_key_id:
            assert isinstance(self.aws_access_key_id, SecretStr)
            kw["aws_access_key_id"] = self.aws_access_key_id.get_secret_value()
        if self.aws_secret_access_key:
            assert isinstance(self.aws_secret_access_key, SecretStr)
            kw["aws_secret_access_key"] = self.aws_secret_access_key.get_secret_value()
        if self.aws_session_token:
            assert isinstance(self.aws_session_token, SecretStr)
            kw["aws_session_token"] = self.aws_session_token.get_secret_value()
        if self.aws_region_name:
            kw["aws_region_name"] = self.aws_region_name
        if self.aws_profile_name:
            kw["aws_profile_name"] = self.aws_profile_name
        if self.aws_role_name:
            kw["aws_role_name"] = self.aws_role_name
        if self.aws_session_name:
            kw["aws_session_name"] = self.aws_session_name
        if self.aws_bedrock_runtime_endpoint:
            kw["aws_bedrock_runtime_endpoint"] = self.aws_bedrock_runtime_endpoint
        return kw

    def _retry_listener_fn(self, attempt_number: int, num_retries: int, _err: BaseException | None) -> None:
        if self.retry_listener is not None:
            self.retry_listener(attempt_number, num_retries, _err)

    @field_serializer("api_key", "aws_access_key_id", "aws_secret_access_key", "aws_session_token", when_used="always",)
    def _serialize_secrets(self, v: SecretStr | None, info):
        return serialize_secret(v, info)

    @property
    def metrics(self) -> Metrics:
        if self._metrics is None:
            self._metrics = Metrics(model_name=self.model)
        return self._metrics

    @property
    def telemetry(self) -> Telemetry:
        if self._telemetry is None:
            self._telemetry = Telemetry(
                model_name=self.model,
                log_enabled=self.log_completions,
                log_dir=self.log_completions_folder if self.log_completions else None,
                input_cost_per_token=self.input_cost_per_token,
                output_cost_per_token=self.output_cost_per_token,
                metrics=self.metrics,
            )
        return self._telemetry

    @property
    def is_subscription(self) -> bool:
        return self._is_subscription

    def restore_metrics(self, metrics: Metrics) -> None:
        self._metrics = metrics
        if self._telemetry is not None:
            self._telemetry.metrics = metrics

    def reset_metrics(self) -> None:
        self._metrics = None
        self._telemetry = None

    def _handle_error(self, error: Exception, fallback_call_fn: Callable[[Driver], LLMResponse]) -> LLMResponse:
        assert self._telemetry is not None
        self._telemetry.on_error(error)
        if self.fallback_strategy and self.fallback_strategy.should_fallback(error):
            result = self.fallback_strategy.try_fallback(
                primary_model=self.model,
                primary_error=error,
                primary_metrics=self.metrics,
                call_fn=fallback_call_fn,
            )
            if result is not None:
                return result
        mapped = map_provider_exception(error)
        if mapped is not error:
            raise mapped from error
        raise

    def completion(
        self,
        messages: list[Message],
        tools: Sequence[ToolDefinition] | None = None,
        _return_metrics: bool = False,
        add_security_risk_prediction: bool = False,
        on_token: TokenCallbackType | None = None,
        **kwargs,
    ) -> LLMResponse:
        """DriverIO 컨트롤러로 위임"""
        assert self._io is not None
        return self._io.completion(
            messages=messages,
            tools=tools,
            _return_metrics=_return_metrics,
            add_security_risk_prediction=add_security_risk_prediction,
            on_token=on_token,
            **kwargs
        )

    def responses(
        self,
        messages: list[Message],
        tools: Sequence[ToolDefinition] | None = None,
        include: list[str] | None = None,
        store: bool | None = None,
        _return_metrics: bool = False,
        add_security_risk_prediction: bool = False,
        on_token: TokenCallbackType | None = None,
        **kwargs,
    ) -> LLMResponse:
        """DriverIO 컨트롤러로 위임"""
        assert self._io is not None
        return self._io.responses(
            messages=messages,
            tools=tools,
            include=include,
            store=store,
            _return_metrics=_return_metrics,
            add_security_risk_prediction=add_security_risk_prediction,
            on_token=on_token,
            **kwargs
        )

    ## Transport + helpers
    def _infer_litellm_provider(self) -> str | None:
        if self._litellm_provider is not None:
            return self._litellm_provider

        provider = DriverFactory.infer_provider(model=self.model, api_base=self.base_url)
        self._litellm_provider = provider
        return provider

    def _get_litellm_api_key_value(self) -> str | None:
        api_key_value: str | None = None
        if self.api_key:
            assert isinstance(self.api_key, SecretStr)
            api_key_value = self.api_key.get_secret_value()

        if api_key_value is not None and self._infer_litellm_provider() == "bedrock":
            return None

        return api_key_value

    def _transport_call(
        self,
        *,
        messages: list[dict[str, Any]],
        enable_streaming: bool = False,
        on_token: TokenCallbackType | None = None,
        **kwargs,
    ) -> ModelResponse:
        # litellm.modify_params is GLOBAL; guard it for thread-safety
        with self._litellm_modify_params_ctx(self.modify_params):
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=DeprecationWarning, module="httpx.*")
                warnings.filterwarnings(
                    "ignore",
                    message=r".*content=.*upload.*",
                    category=DeprecationWarning,
                )
                warnings.filterwarnings(
                    "ignore",
                    message=r"There is no current event loop",
                    category=DeprecationWarning,
                )
                warnings.filterwarnings("ignore", category=UserWarning,)
                warnings.filterwarnings(
                    "ignore",
                    category=DeprecationWarning,
                    message="Accessing the 'model_fields' attribute.*",
                )
                api_key_value = self._get_litellm_api_key_value()

                merged_kwargs = {**self._aws_kwargs(), **kwargs}
                merged_kwargs.pop("base_model", None)

                # Some providers need renames handled in _normalize_call_kwargs.
                ret = litellm_completion(
                    model=self.model,
                    api_key=api_key_value,
                    api_base=self.base_url,
                    api_version=self.api_version,
                    timeout=self.timeout,
                    drop_params=self.drop_params,
                    seed=self.seed,
                    messages=messages,
                    **merged_kwargs,
                    # **{**self._aws_kwargs(), **kwargs},
                )
                if enable_streaming and on_token is not None:
                    assert isinstance(ret, CustomStreamWrapper)
                    chunks = []
                    for chunk in ret:
                        on_token(chunk)
                        chunks.append(chunk)
                    ret = stream_chunk_builder(chunks, messages=messages)

                assert isinstance(ret, ModelResponse), (
                    f"Expected ModelResponse, got {type(ret)}"
                )
                return ret

    @contextmanager
    def _litellm_modify_params_ctx(self, flag: bool):
        old = config.modify_params
        try:
            config.modify_params = flag
            yield
        finally:
            config.modify_params = old

    ## Capabilities, formatting, and info
    def _model_name_for_capabilities(self) -> str:
        return self.model_canonical_name or self.model

    def _validate_context_window_size(self) -> None:
        if os.environ.get(ENV_ALLOW_SHORT_CONTEXT_WINDOWS, "").lower() in ("true", "1", "yes",):
            return

        if self.max_input_tokens is None:
            return

        if self.max_input_tokens < MIN_CONTEXT_WINDOW_TOKENS:
            raise LLMContextWindowTooSmallError(self.max_input_tokens, MIN_CONTEXT_WINDOW_TOKENS)

    def vision_is_active(self) -> bool:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return not self.disable_vision and self._supports_vision()

    def _supports_vision(self) -> bool:
        model_for_caps = self._model_name_for_capabilities()
        return (
            supports_vision(model_for_caps)
            or supports_vision(model_for_caps.split("/")[-1])
            or (
                self._model_info is not None
                and self._model_info.get("supports_vision", False)
            )
            or False  # fallback to False if model_info is None
        )

    def is_caching_prompt_active(self) -> bool:
        if not self.caching_prompt:
            return False
        return (
            self.caching_prompt
            and get_features(self._model_name_for_capabilities()).supports_prompt_cache
        )

    def uses_responses_api(self) -> bool:
        return get_features(self._model_name_for_capabilities()).supports_responses_api

    @property
    def model_info(self) -> dict | None:
        """Returns the model info dictionary."""
        return self._model_info

    ## Utilities preserved from previous class
    def _apply_prompt_caching(self, messages: list[Message]) -> None:
        if len(messages) > 0 and messages[0].role == "system":
            sys_content = messages[0].content
            if len(sys_content) >= 2:
                ## Two-block structure: static (index 0) + dynamic (index 1) Mark only the static block; ensure dynamic is unmarked
                sys_content[0].cache_prompt = True
                sys_content[1].cache_prompt = False
            elif len(sys_content) == 1:
                ## Single block: mark it for caching
                sys_content[0].cache_prompt = True

        ## NOTE: this is only needed for anthropic
        for message in reversed(messages):
            if message.role in ("user", "tool"):
                message.content[
                    -1
                ].cache_prompt = True  # Last item inside the message content
                break

    def format_messages_for_llm(self, messages: list[Message]) -> list[dict]:
        """Formats Message objects for LLM consumption."""
        messages = copy.deepcopy(messages)
        if self.is_caching_prompt_active():
            self._apply_prompt_caching(messages)

        model_features = get_features(self._model_name_for_capabilities())
        cache_enabled = self.is_caching_prompt_active()
        vision_enabled = self.vision_is_active()
        function_calling_enabled = self.native_tool_calling
        force_string_serializer = (
            self.force_string_serializer
            if self.force_string_serializer is not None
            else model_features.force_string_serializer
        )
        send_reasoning_content = model_features.send_reasoning_content
        formatted_messages = [
            message.to_chat_dict(
                cache_enabled=cache_enabled,
                vision_enabled=vision_enabled,
                function_calling_enabled=function_calling_enabled,
                force_string_serializer=force_string_serializer,
                send_reasoning_content=send_reasoning_content,
            )
            for message in messages
        ]
        return formatted_messages

    def format_messages_for_responses(
        self, messages: list[Message]
    ) -> tuple[str | None, list[dict[str, Any]]]:
        msgs = copy.deepcopy(messages)
        vision_active = self.vision_is_active()
        instructions: str | None = None
        input_items: list[dict[str, Any]] = []
        system_chunks: list[str] = []

        for m in msgs:
            val = m.to_responses_value(vision_enabled=vision_active)
            if isinstance(val, str):
                s = val.strip()
                if s:
                    if self.is_subscription:
                        system_chunks.append(s)
                    else:
                        instructions = (
                            s
                            if instructions is None
                            else f"{instructions}\n\n---\n\n{s}"
                        )
            elif val:
                input_items.extend(val)

        if self.is_subscription:
            return transform_for_subscription(system_chunks, input_items)
        return instructions, input_items

    def get_token_count(self, messages: list[Message]) -> int:
        log.debug("Message objects now include serialized tool calls in token counting")
        formatted_messages = self.format_messages_for_llm(messages)
        try:
            return int(token_counter(model=self.model, messages=formatted_messages, custom_tokenizer=self._tokenizer,))
        except Exception as e:
            log.error(
                f"Error getting token count for model {self.model}\n{e}"
                + (
                    f"\ncustom_tokenizer: {self.custom_tokenizer}"
                    if self.custom_tokenizer
                    else ""
                ),
                exc_info=True,
            )
            return 0