# channel.driver
import copy
import warnings
from typing import TYPE_CHECKING, Any, Sequence, cast, Final
from channel.bound.completion import completion as litellm_completion
from channel.bound.handler.response.main import responses as litellm_responses
from agent.call.exceptions.types import LLMNoResponseError
from channel.llm.response import LLMResponse
from channel.switch.params import Delta, ModelResponseStream, StreamingChoices
from channel.switch.params import ModelResponse
from channel.switch.params import ChatCompletionToolParam
from agent.call.tool.message import Message
from agent.manager.option.chat import select_chat_options
from gate.exceptions import (
    APIConnectionError,
    InternalServerError,
    RateLimitError,
    ServiceUnavailableError,
    Timeout as LiteLLMTimeout,
)
from meta.watcher.tracker.conv.metrics import MetricsSnapshot
if TYPE_CHECKING:
    from channel.llm.driver import Driver
    from agent.call.types import TokenCallbackType
    from agent.call.tool.redef import ToolDefinition

LLM_RETRY_EXCEPTIONS: Final[tuple[type[Exception], ...]] = (
    APIConnectionError,
    RateLimitError,
    ServiceUnavailableError,
    LiteLLMTimeout,
    InternalServerError,
    LLMNoResponseError,
)

class DriverIO:
    def __init__(self, driver: "Driver"):
        self.driver = driver

    def completion(
        self,
        messages: list[Message],
        tools: Sequence["ToolDefinition"] | None = None,
        _return_metrics: bool = False,
        add_security_risk_prediction: bool = False,
        on_token: "TokenCallbackType | None" = None,
        **kwargs,
    ) -> LLMResponse:
        enable_streaming = bool(kwargs.get("stream", False)) or self.driver.stream
        if enable_streaming and on_token is None:
            raise ValueError("Streaming requires an on_token callback")
        if enable_streaming:
            kwargs["stream"] = True

        formatted_messages = self.driver.format_messages_for_llm(messages)
        
        ## 툴 스키마 변환 및 바인딩
        cc_tools = []
        if tools:
            cc_tools = [
                t.to_openai_tool(add_security_risk_prediction=add_security_risk_prediction)
                for t in tools
            ]
        
        use_mock_tools = self.driver.should_mock_tool_calls(cc_tools)
        if use_mock_tools:
            formatted_messages, kwargs = self.driver.pre_request_prompt_mock(
                formatted_messages, cc_tools or [], kwargs
            )

        kwargs["tools"] = cc_tools if (bool(cc_tools) and self.driver.native_tool_calling) else None
        enable_streaming = bool(kwargs.get("stream", False)) or self.driver.stream
        if enable_streaming:
            if on_token is None:
                raise ValueError("Streaming requires an on_token callback")
            kwargs["stream"] = True

        ## serialize messages
        formatted_messages = self.driver.format_messages_for_llm(messages)

        ## choose function-calling strategy
        use_native_fc = self.driver.native_tool_calling
        original_fncall_msgs = copy.deepcopy(formatted_messages)

        ## Convert Tool objects to ChatCompletionToolParam once here
        cc_tools: list[ChatCompletionToolParam] = []
        if tools:
            cc_tools = [
                t.to_openai_tool(
                    add_security_risk_prediction=add_security_risk_prediction,
                )
                for t in tools
            ]

        use_mock_tools = self.driver.should_mock_tool_calls(cc_tools)
        if use_mock_tools:
            log.debug(f"LLM.completion: mocking function-calling via prompt for model {self.driver.model}")
            formatted_messages, kwargs = self.driver.pre_request_prompt_mock(formatted_messages, cc_tools or [], kwargs)

        ## normalize provider params - Only pass tools when native FC is active
        kwargs["tools"] = cc_tools if (bool(cc_tools) and use_native_fc) else None
        has_tools_flag = bool(cc_tools) and use_native_fc
        call_kwargs = select_chat_options(self.driver, kwargs, has_tools=has_tools_flag)

        ## request context for telemetry (always include context_window for metrics)
        assert self.driver._telemetry is not None
        ## Always pass context_window so metrics are tracked even when logging disabled
        telemetry_ctx: dict[str, Any] = {"context_window": self.driver.max_input_tokens or 0}
        if self.driver._telemetry.log_enabled:
            telemetry_ctx.update(
                {
                    "messages": formatted_messages[:],  # already simple dicts
                    "tools": tools,
                    "kwargs": {k: v for k, v in call_kwargs.items()},
                }
            )
            if tools and not use_native_fc:
                telemetry_ctx["raw_messages"] = original_fncall_msgs

        ## do the call with retries
        @self.driver.retry_decorator(
            num_retries=self.driver.num_retries,
            retry_exceptions=LLM_RETRY_EXCEPTIONS,
            retry_min_wait=self.driver.retry_min_wait,
            retry_max_wait=self.driver.retry_max_wait,
            retry_multiplier=self.driver.retry_multiplier,
            retry_listener=self.driver._retry_listener_fn,
        )
        def _one_attempt(**retry_kwargs) -> ModelResponse:
            assert self.driver._telemetry is not None
            self.driver._telemetry.on_request(telemetry_ctx=telemetry_ctx)
            # Merge retry-modified kwargs (like temperature) with call_kwargs
            final_kwargs = {**call_kwargs, **retry_kwargs}
            resp = self.driver._transport_call(
                messages=formatted_messages,
                **final_kwargs,
                enable_streaming=enable_streaming,
                on_token=on_token,
            )
            raw_resp: ModelResponse | None = None
            if use_mock_tools:
                raw_resp = copy.deepcopy(resp)
                resp = self.driver.post_response_prompt_mock(
                    resp, nonfncall_msgs=formatted_messages, tools=cc_tools
                )

            ## @telemetry
            self.driver._telemetry.on_response(resp, raw_resp=raw_resp)

            ## Ensure at least one choice.
            # Gemini sometimes returns empty choices; we raise LLMNoResponseError here inside the retry boundary so it is retried.
            if not resp.get("choices") or len(resp["choices"]) < 1:
                raise LLMNoResponseError("Response choices is less than 1. Response: " + str(resp))
            return resp

        try:
            resp = _one_attempt()
            first_choice = resp["choices"][0]
            message = Message.from_llm_chat_message(first_choice["message"])

            # Get current metrics snapshot
            metrics_snapshot = MetricsSnapshot(
                model_name=self.driver.metrics.model_name,
                accumulated_cost=self.driver.metrics.accumulated_cost,
                max_budget_per_task=self.driver.metrics.max_budget_per_task,
                accumulated_token_usage=self.driver.metrics.accumulated_token_usage,
            )
            # Create and return LLMResponse
            return LLMResponse(message=message, metrics=metrics_snapshot, raw_response=resp)
        except Exception as e:
            return self.driver._handle_error(
                e,
                lambda fb: fb.completion(
                    messages,
                    tools,
                    _return_metrics,
                    add_security_risk_prediction,
                    on_token,
                ),
            )
        raise NotImplementedError("기존 Driver.completion 내부의 I/O 로직을 이곳에 복사합니다.")

    def responses(
        self,
        messages: list[Message],
        tools: Sequence["ToolDefinition"] | None = None,
        include: list[str] | None = None,
        store: bool | None = None,
        _return_metrics: bool = False,
        add_security_risk_prediction: bool = False,
        on_token: "TokenCallbackType | None" = None,
        **kwargs,
    ) -> LLMResponse:
        user_enable_streaming = bool(kwargs.get("stream", False)) or self.driver.stream
        if user_enable_streaming:
            if on_token is None and not self.is_subscription:
                # We allow on_token to be None for subscription mode
                raise ValueError("Streaming requires an on_token callback")
            kwargs["stream"] = True

        ## Build instructions + input list using dedicated Responses formatter
        instructions, input_items = self.driver.format_messages_for_responses(messages)
        resp_tools = (
            [
                t.to_responses_tool(
                    add_security_risk_prediction=add_security_risk_prediction,
                )
                for t in tools
            ]
            if tools
            else None
        )

        ## Normalize/override Responses kwargs consistently
        call_kwargs = select_responses_options(self.driver, kwargs, include=include, store=store)
        ## Request context for telemetry (always include context_window for metrics)
        assert self.driver._telemetry is not None
        ## Always pass context_window so metrics are tracked even when logging disabled
        telemetry_ctx: dict[str, Any] = {"context_window": self.driver.max_input_tokens or 0}
        if self.driver._telemetry.log_enabled:
            telemetry_ctx.update(
                {
                    "llm_path": "responses",
                    "instructions": instructions,
                    "input": input_items[:],
                    "tools": tools,
                    "kwargs": {k: v for k, v in call_kwargs.items()},
                }
            )

        # Perform call with retries
        @self.retry_decorator(
            num_retries=self.driver.num_retries,
            retry_exceptions=LLM_RETRY_EXCEPTIONS,
            retry_min_wait=self.driver.retry_min_wait,
            retry_max_wait=self.driver.retry_max_wait,
            retry_multiplier=self.driver.retry_multiplier,
            retry_listener=self.driver._retry_listener_fn,
        )
        def _one_attempt(**retry_kwargs) -> ResponsesAPIResponse:
            assert self.driver._telemetry is not None
            self.driver._telemetry.on_request(telemetry_ctx=telemetry_ctx)
            final_kwargs = {**call_kwargs, **retry_kwargs}
            with self.driver._litellm_modify_params_ctx(self.driver.modify_params):
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", category=DeprecationWarning)
                    typed_input: ResponseInputParam | str = (
                        cast(ResponseInputParam, input_items) if input_items else ""
                    )
                    api_key_value = self.driver._get_litellm_api_key_value()

                    ret = litellm_responses(
                        model=self.driver.model,
                        input=typed_input,
                        instructions=instructions,
                        tools=resp_tools,
                        api_key=api_key_value,
                        api_base=self.driver.base_url,
                        api_version=self.driver.api_version,
                        timeout=self.driver.timeout,
                        drop_params=self.driver.drop_params,
                        seed=self.driver.seed,
                        **{**self.driver._aws_kwargs(), **final_kwargs},
                    )
                    if isinstance(ret, ResponsesAPIResponse):
                        if user_enable_streaming:
                            log.warning(
                                "Responses streaming was requested, but the provider "
                                "returned a non-streaming response; no on_token deltas "
                                "will be emitted."
                            )
                        self.driver._telemetry.on_response(ret)
                        return ret

                    # When stream=True, LiteLLM returns a streaming iterator rather than
                    # a single ResponsesAPIResponse. Drain the iterator and use the
                    # completed response.
                    if final_kwargs.get("stream", False):
                        if not isinstance(ret, SyncResponsesAPIStreamingIterator):
                            raise AssertionError(
                                f"Expected Responses stream iterator, got {type(ret)}"
                            )

                        stream_callback = on_token if user_enable_streaming else None
                        for event in ret:
                            if stream_callback is None:
                                continue
                            if isinstance(
                                event,
                                (
                                    OutputTextDeltaEvent,
                                    RefusalDeltaEvent,
                                    ReasoningSummaryTextDeltaEvent,
                                ),
                            ):
                                delta = event.delta
                                if delta:
                                    # stream_callback(
                                    #     {
                                    #         "object": "chat.completion.chunk",
                                    #         "choices": [
                                    #             {"delta": {"content": delta}}
                                    #         ]
                                    #     }
                                    # )
                                    stream_callback(ModelResponseStream(choices=[StreamingChoices(delta=Delta(content=delta))]))
                        completed_event = ret.completed_response
                        if completed_event is None:
                            raise LLMNoResponseError(
                                "Responses stream finished without a completed response"
                            )
                        if not isinstance(completed_event, ResponseCompletedEvent):
                            raise LLMNoResponseError(
                                f"Unexpected completed event: {type(completed_event)}"
                            )

                        completed_resp = completed_event.response
                        self.driver._telemetry.on_response(completed_resp)
                        return completed_resp
                    raise AssertionError(f"Expected ResponsesAPIResponse, got {type(ret)}")

        try:
            resp: ResponsesAPIResponse = _one_attempt()
            output_seq = cast(Sequence[Any], resp.output or [])
            message = Message.from_llm_responses_output(output_seq)
            metrics_snapshot = MetricsSnapshot(
                model_name=self.driver.metrics.model_name,
                accumulated_cost=self.driver.metrics.accumulated_cost,
                max_budget_per_task=self.driver.metrics.max_budget_per_task,
                accumulated_token_usage=self.driver.metrics.accumulated_token_usage,
            )
            return LLMResponse(message=message, metrics=metrics_snapshot, raw_response=resp)
        except Exception as e:
            return self._handle_error(
                e,
                lambda fb: fb.responses(
                    messages,
                    tools,
                    include,
                    store,
                    _return_metrics,
                    add_security_risk_prediction,
                    on_token,
                ),
            )