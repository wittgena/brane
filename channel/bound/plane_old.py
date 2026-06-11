# channel.bound.plane_old
## @lineage: channel.bound.plane
import copy
import datetime
import json
import os
import re
import subprocess
import sys
import time
import traceback
from datetime import datetime as dt_object
from functools import lru_cache
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    List,
    Literal,
    Optional,
    Tuple,
    Type,
    Union,
    cast,
)
from httpx import Response
from pydantic import BaseModel

import litellm
from litellm import (
    _custom_logger_compatible_callbacks_literal,
    json_logs,
    log_raw_request_response,
    turn_off_message_logging,
)
from litellm.caching.caching import DualCache, InMemoryCache
from litellm.types.mcp import MCPPostCallResponseObject
from litellm.types.prompts.init_prompts import PromptSpec
from litellm.litellm_core_utils.specialty_caches.dynamic_logging_cache import DynamicLoggingCache
if TYPE_CHECKING:
    from litellm.llms.base_llm.passthrough.transformation import BasePassthroughConfig

from anchor.model.types.utils import (
    CallTypes,
    CostResponseTypes,
    CustomPricingLiteLLMParams,
    EmbeddingResponse,
    GuardrailStatus,
    ImageResponse,
    LiteLLMLoggingBaseClass,
    LiteLLMRealtimeStreamLoggingObject,
    ModelResponse,
    ModelResponseStream,
    RawRequestTypedDict,
    StandardBuiltInToolsParams,
    StandardCallbackDynamicParams,
    StandardLoggingAdditionalHeaders,
    StandardLoggingHiddenParams,
    StandardLoggingMCPToolCall,
    StandardLoggingMetadata,
    StandardLoggingModelCostFailureDebugInformation,
    StandardLoggingModelInformation,
    StandardLoggingPayload,
    StandardLoggingPayloadErrorInformation,
    StandardLoggingPayloadStatus,
    StandardLoggingPayloadStatusFields,
    StandardLoggingPromptManagementMetadata,
    StandardLoggingVectorStoreRequest,
    TextCompletionResponse,
    TranscriptionResponse,
    Usage,
)
from gate._uuid import uuid
from gate.constants import (
    DEFAULT_MOCK_RESPONSE_COMPLETION_TOKEN_COUNT,
    DEFAULT_MOCK_RESPONSE_PROMPT_TOKEN_COUNT,
    SENTRY_DENYLIST,
    SENTRY_PII_DENYLIST,
)
from anchor.model.types.llms.openai import (
    AllMessageValues,
    Batch,
    FineTuningJob,
    HttpxBinaryResponseContent,
    OpenAIFileObject,
    OpenAIModerationResponse,
    ResponseAPIUsage,
    ResponseCompletedEvent,
    ResponseFailedEvent,
    ResponseIncompleteEvent,
    ResponsesAPIResponse,
)
from channel.gate import _get_base_model_from_metadata
from channel.bound.litellm.exception_mapping_utils import _get_response_headers
from watcher.plane.emitter import get_emitter

log = get_emitter("voider")

CustomLogger = Any

GenericAPILogger = CustomLogger  # type: ignore
ResendEmailLogger = CustomLogger  # type: ignore
SendGridEmailLogger = CustomLogger  # type: ignore
SMTPEmailLogger = CustomLogger  # type: ignore
PagerDutyAlerting = CustomLogger  # type: ignore
EnterpriseCallbackControls = None  # type: ignore
EnterpriseStandardLoggingPayloadSetupVAR = None
_in_memory_loggers: List[Any] = []

_STANDARD_LOGGING_METADATA_KEYS: frozenset = frozenset(
    StandardLoggingMetadata.__annotations__.keys()
)

# Cache custom pricing keys as frozenset for O(1) lookups instead of looping through 49 keys
_CUSTOM_PRICING_KEYS: frozenset = frozenset(
    CustomPricingLiteLLMParams.model_fields.keys()
)

sentry_sdk_instance = None
capture_exception = None
add_breadcrumb = None
slack_app = None
alerts_channel = None
heliconeLogger = None
athinaLogger = None
promptLayerLogger = None
logfireLogger = None
weightsBiasesLogger = None
customLogger = None
langFuseLogger = None
openMeterLogger = None
lagoLogger = None
dataDogLogger = None
prometheusLogger = None
dynamoLogger = None
s3Logger = None
greenscaleLogger = None
lunaryLogger = None
supabaseClient = None
deepevalLogger = None
callback_list: Optional[List[str]] = []
user_logger_fn = None
additional_details: Optional[Dict[str, str]] = {}
local_cache: Optional[Dict[str, str]] = {}
last_fetched_at = None
last_fetched_at_keys = None


####
class ServiceTraceIDCache:
    def __init__(self) -> None:
        self.cache = InMemoryCache()

    def get_cache(self, litellm_call_id: str, service_name: str) -> Optional[str]:
        key_name = "{}:{}".format(service_name, litellm_call_id)
        response = self.cache.get_cache(key=key_name)
        return response

    def set_cache(self, litellm_call_id: str, service_name: str, trace_id: str) -> None:
        key_name = "{}:{}".format(service_name, litellm_call_id)
        self.cache.set_cache(key=key_name, value=trace_id)
        return None


in_memory_trace_id_cache = ServiceTraceIDCache()
in_memory_dynamic_logger_cache = DynamicLoggingCache()

# Cached lazy import for PrometheusLogger
# Module-level cache to avoid repeated imports while preserving memory benefits
_PrometheusLogger = None


def _get_cached_prometheus_logger():
    """
    Get cached PrometheusLogger class.
    Lazy imports on first call to avoid loading prometheus.py and utils.py at import time (60MB saved).
    Subsequent calls use cached class for better performance.
    """
    global _PrometheusLogger
    if _PrometheusLogger is None:
        from litellm.integrations.prometheus import PrometheusLogger

        _PrometheusLogger = PrometheusLogger
    return _PrometheusLogger


class Logging(LiteLLMLoggingBaseClass):
    custom_pricing: bool = False
    stream_options = None
    litellm_request_debug: bool = False

    def __init__(
        self,
        model: str,
        messages,
        stream,
        call_type,
        start_time,
        litellm_call_id: str,
        function_id: str,
        litellm_trace_id: Optional[str] = None,
        dynamic_input_callbacks: Optional[
            List[Union[str, Callable, CustomLogger]]
        ] = None,
        dynamic_success_callbacks: Optional[
            List[Union[str, Callable, CustomLogger]]
        ] = None,
        dynamic_async_success_callbacks: Optional[
            List[Union[str, Callable, CustomLogger]]
        ] = None,
        dynamic_failure_callbacks: Optional[
            List[Union[str, Callable, CustomLogger]]
        ] = None,
        dynamic_async_failure_callbacks: Optional[
            List[Union[str, Callable, CustomLogger]]
        ] = None,
        applied_guardrails: Optional[List[str]] = None,
        kwargs: Optional[Dict] = None,
        log_raw_request_response: bool = False,
    ):
        self._defer_async_logging: bool = False
        self._enqueue_deferred_logging: Optional[Callable[[], None]] = None

    def process_dynamic_callbacks(self):
        pass

    def _process_dynamic_callback_list(
        self,
        callback_list: Optional[List[Union[str, Callable, CustomLogger]]],
        dynamic_callbacks_type: Literal[
            "input", "success", "failure", "async_success", "async_failure"
        ],
    ) -> Optional[List[Union[str, Callable, CustomLogger]]]:
        return None

    def get_router_model_id(self) -> Optional[str]:
        return None

    def update_environment_variables(
        self,
        litellm_params: Dict,
        optional_params: Dict,
        model: Optional[str] = None,
        user: Optional[str] = None,
        **additional_params,
    ):
        pass

    def update_from_kwargs(
        self,
        kwargs: Dict,
        litellm_params: Optional[Dict] = None,
        optional_params: Optional[Dict] = None,
        model: Optional[str] = None,
        user: Optional[str] = None,
        **additional_params,
    ):
        pass

    def update_messages(self, messages: List[AllMessageValues]):
        self.messages = messages
        self.model_call_details["messages"] = messages

    def should_run_prompt_management_hooks(
        self,
        non_default_params: Dict,
        prompt_id: Optional[str] = None,
        tools: Optional[List[Dict]] = None,
    ) -> bool:
        return False

    def _should_run_prompt_management_hooks_without_prompt_id(
        self,
        non_default_params: Dict,
        tools: Optional[List[Dict]] = None,
    ) -> bool:
        return False

    def get_chat_completion_prompt(
        self,
        model: str,
        messages: List[AllMessageValues],
        non_default_params: Dict,
        prompt_variables: Optional[dict],
        prompt_id: Optional[str] = None,
        prompt_spec: Optional[PromptSpec] = None,
        prompt_management_logger: Optional[CustomLogger] = None,
        prompt_label: Optional[str] = None,
        prompt_version: Optional[int] = None,
    ) -> Tuple[str, List[AllMessageValues], dict]:
        return model, messages, non_default_params

    async def async_get_chat_completion_prompt(
        self,
        model: str,
        messages: List[AllMessageValues],
        non_default_params: Dict,
        prompt_variables: Optional[dict],
        prompt_id: Optional[str] = None,
        prompt_spec: Optional[PromptSpec] = None,
        prompt_management_logger: Optional[CustomLogger] = None,
        tools: Optional[List[Dict]] = None,
        prompt_label: Optional[str] = None,
        prompt_version: Optional[int] = None,
    ) -> Tuple[str, List[AllMessageValues], dict]:
        return model, messages, non_default_params

    def _auto_detect_prompt_management_logger(
        self,
        prompt_id: str,
        prompt_spec: Optional[PromptSpec],
        dynamic_callback_params: StandardCallbackDynamicParams,
    ) -> Optional[CustomLogger]:
        return None

    def get_custom_logger_for_prompt_management(
        self,
        model: str,
        non_default_params: Dict,
        tools: Optional[List[Dict]] = None,
        prompt_id: Optional[str] = None,
        prompt_spec: Optional[PromptSpec] = None,
        dynamic_callback_params: Optional[StandardCallbackDynamicParams] = None,
    ) -> Optional[CustomLogger]:
        return None

    def get_custom_logger_for_anthropic_cache_control_hook(
        self, non_default_params: Dict
    ) -> Optional[CustomLogger]:
        return None

    def _get_raw_request_body(self, data: Optional[Union[dict, str]]) -> dict:
        return data

    def _get_masked_api_base(self, api_base: str) -> str:
        if "key=" in api_base:
            # Find the position of "key=" in the string
            key_index = api_base.find("key=") + 4
            # Mask the last 5 characters after "key="
            masked_api_base = api_base[:key_index] + "*" * 5 + api_base[-4:]
        else:
            masked_api_base = api_base
        return str(masked_api_base)

    def _pre_call(self, input, api_key, model=None, additional_args={}):
        pass

    def pre_call(self, input, api_key, model=None, additional_args={}):  # noqa: PLR0915
        pass

    def _print_llm_call_debugging_log(
        self,
        api_base: str,
        headers: dict,
        additional_args: dict,
    ):
        headers = additional_args.get("headers", {})
        if headers is None:
            headers = {}
        data = additional_args.get("complete_input_dict", {})
        api_base = str(additional_args.get("api_base", ""))
        curl_command = self._get_request_curl_command(
            api_base=api_base,
            headers=headers,
            additional_args=additional_args,
            data=data,
        )
        log.debug(f"\033[92m{curl_command}\033[0m\n")

    def _get_request_body(self, data: dict) -> str:
        return str(data)

    def _get_request_curl_command(
        self, api_base: str, headers: Optional[dict], additional_args: dict, data: dict
    ) -> str:
        masked_api_base = self._get_masked_api_base(api_base)
        if headers is None:
            headers = {}
        curl_command = "\n\nPOST Request Sent from LiteLLM:\n"
        curl_command += "curl -X POST \\\n"
        curl_command += f"{masked_api_base} \\\n"
        masked_headers = self._get_masked_headers(headers)
        formatted_headers = " ".join(
            [f"-H '{k}: {v}'" for k, v in masked_headers.items()]
        )
        curl_command += (
            f"{formatted_headers} \\\n" if formatted_headers.strip() != "" else ""
        )
        curl_command += f"-d '{self._get_request_body(data)}'\n"
        if additional_args.get("request_str", None) is not None:
            # print the sagemaker / bedrock client request
            curl_command = "\nRequest Sent from LiteLLM:\n"
            request_str = additional_args.get("request_str", "")
            curl_command += request_str
        elif api_base == "":
            curl_command = str(self.model_call_details)
        return curl_command

    def _get_masked_headers(
        self, headers: dict, ignore_sensitive_headers: bool = False
    ) -> dict:
        return _get_masked_values(
            headers, ignore_sensitive_values=ignore_sensitive_headers
        )

    def post_call(self, original_response, input=None, api_key=None, additional_args={}):
        pass

    async def async_post_mcp_tool_call_hook(
        self,
        kwargs: dict,
        response_obj: Any,
        start_time: datetime.datetime,
        end_time: datetime.datetime,
    ):
        return response_obj

    def _parse_post_mcp_call_hook_response(self, response: Optional[MCPPostCallResponseObject]) -> Any:
        if response is None:
            return None
        self.model_call_details["response_cost"] = response.hidden_params.response_cost
        return response.mcp_tool_call_response

    def get_response_ms(self) -> float:
        return (
            self.model_call_details.get("end_time", datetime.datetime.now())
            - self.model_call_details.get("start_time", datetime.datetime.now())
        ).total_seconds() * 1000

    def set_cost_breakdown(
        self,
        input_cost: float,
        output_cost: float,
        total_cost: float,
        cost_for_built_in_tools_cost_usd_dollar: float,
        additional_costs: Optional[dict] = None,
        original_cost: Optional[float] = None,
        discount_percent: Optional[float] = None,
        discount_amount: Optional[float] = None,
        margin_percent: Optional[float] = None,
        margin_fixed_amount: Optional[float] = None,
        margin_total_amount: Optional[float] = None,
        cache_read_cost: Optional[float] = None,
        cache_creation_cost: Optional[float] = None,
    ) -> None:
        return None

    def _response_cost_calculator(
        self,
        result: Union[
            ModelResponse,
            ModelResponseStream,
            EmbeddingResponse,
            ImageResponse,
            TranscriptionResponse,
            TextCompletionResponse,
            HttpxBinaryResponseContent,
            Batch,
            FineTuningJob,
            ResponsesAPIResponse,
            ResponseCompletedEvent,
            OpenAIFileObject,
            LiteLLMRealtimeStreamLoggingObject,
            OpenAIModerationResponse,
            dict,
            list,
        ],
        cache_hit: Optional[bool] = None,
        litellm_model_name: Optional[str] = None,
        router_model_id: Optional[str] = None,
    ) -> Optional[float]:
        return 0.0

    async def _response_cost_calculator_async(
        self,
        result: Union[
            ModelResponse,
            ModelResponseStream,
            EmbeddingResponse,
            ImageResponse,
            TranscriptionResponse,
            TextCompletionResponse,
            HttpxBinaryResponseContent,
            Batch,
            FineTuningJob,
        ],
        cache_hit: Optional[bool] = None,
    ) -> Optional[float]:
        return self._response_cost_calculator(result=result, cache_hit=cache_hit)

    @staticmethod
    def _is_sync_litellm_request(litellm_params: dict) -> bool:
        """True for sync SDK entrypoints (``completion``), false for async (``acompletion``, etc.)."""
        return (
            litellm_params.get(CallTypes.acompletion.value, False) is not True
            and litellm_params.get(CallTypes.aresponses.value, False) is not True
            and litellm_params.get(CallTypes.aembedding.value, False) is not True
            and litellm_params.get(CallTypes.aimage_generation.value, False) is not True
            and litellm_params.get(CallTypes.atranscription.value, False) is not True
        )

    def _is_assembled_stream_success(self, result=None) -> bool:
        """Final assembled stream export (not a per-chunk success call).

        Per-chunk callers pass a ``ModelResponseStream`` (or ``None``); the
        final assembled response is any other non-``None`` value (typically a
        ``ModelResponse``). Treating a chunk as the assembled response would
        prematurely set the ``has_dispatched_final_stream_success`` dedup
        guard and silently suppress the real final stream log.
        """
        if self.stream is not True:
            return False
        if result is not None and not isinstance(result, ModelResponseStream):
            return True
        return (
            "async_complete_streaming_response" in self.model_call_details
            or self.model_call_details.get("complete_streaming_response") is not None
        )

    async def dispatch_success_handlers(
        self,
        result=None,
        start_time=None,
        end_time=None,
        cache_hit=None,
        prefer_async_handlers: bool = False,
        **kwargs,
    ) -> None:
        return

    def should_run_logging(
        self,
        event_type: Literal[
            "async_success", "sync_success", "async_failure", "sync_failure"
        ],
        stream: bool = False,
    ) -> bool:
        return False

    def has_run_logging(
        self,
        event_type: Literal[
            "async_success", "sync_success", "async_failure", "sync_failure"
        ],
    ) -> None:
        return

    def should_run_callback(
        self, callback: litellm.CALLBACK_TYPES, litellm_params: dict, event_hook: str
    ) -> bool:
        return False

    def _update_completion_start_time(self, completion_start_time: datetime.datetime):
        self.completion_start_time = completion_start_time
        self.model_call_details["completion_start_time"] = self.completion_start_time

    def normalize_logging_result(self, result: Any) -> Any:
        return result

    def _merge_hidden_params_from_response_into_metadata(
        self, logging_result: Any
    ) -> None:
        pass

    def _process_hidden_params_and_response_cost(
        self,
        logging_result,
        start_time,
        end_time,
    ):
        pass

    def _build_standard_logging_payload(
        self, init_response_obj: Any, start_time: Any, end_time: Any
    ) -> Any:
        """Build StandardLoggingPayload and accumulate its construction time."""
        _start = time.time()
        payload = get_standard_logging_object_payload(
            kwargs=self.model_call_details,
            init_response_obj=init_response_obj,
            start_time=start_time,
            end_time=end_time,
            logging_obj=self,
            status="success",
            standard_built_in_tools_params=self.standard_built_in_tools_params,
        )
        self.callback_duration_ms += (time.time() - _start) * 1000
        return payload

    def _transform_usage_objects(self, result):
        return result

    def _success_handler_helper_fn(
        self,
        result=None,
        start_time=None,
        end_time=None,
        cache_hit=None,
        standard_logging_object: Optional[StandardLoggingPayload] = None,
    ):
        return start_time, end_time, result

    def _is_recognized_call_type_for_logging(
        self,
        logging_result: Any,
    ):
        return False

    def _flush_passthrough_collected_chunks_helper(
        self,
        raw_bytes: List[bytes],
        provider_config: "BasePassthroughConfig",
    ) -> Optional["CostResponseTypes"]:
        return None

    def flush_passthrough_collected_chunks(
        self,
        raw_bytes: List[bytes],
        provider_config: "BasePassthroughConfig",
    ):
        return

    async def async_flush_passthrough_collected_chunks(
        self,
        raw_bytes: List[bytes],
        provider_config: "BasePassthroughConfig",
    ):
        return

    def success_handler(self, result=None, start_time=None, end_time=None, cache_hit=None, **kwargs):
        return

    async def async_success_handler(self, result=None, start_time=None, end_time=None, cache_hit=None, **kwargs):
        return

    def _handle_callback_failure(self, callback: Any):
        pass

    def _failure_handler_helper_fn(self, exception, traceback_exception, start_time=None, end_time=None):
        return start_time, end_time

    async def special_failure_handlers(self, exception: Exception):
        return

    def failure_handler(self, exception, traceback_exception, start_time=None, end_time=None):
        return

    async def async_failure_handler(self, exception, traceback_exception, start_time=None, end_time=None):
        return

    def _get_trace_id(self, service_name: Literal["langfuse"]) -> Optional[str]:
        return None

    def _get_callback_object(self, service_name: Literal["langfuse"]) -> Optional[Any]:
        return None

    def handle_sync_success_callbacks_for_async_calls(
        self,
        result: Any,
        start_time: datetime.datetime,
        end_time: datetime.datetime,
        cache_hit: Optional[Any] = None,
    ) -> None:
        return None

    def _should_run_sync_callbacks_for_async_calls(self) -> bool:
        return False

    def get_combined_callback_list(
        self, dynamic_success_callbacks: Optional[List], global_callbacks: List
    ) -> List:
        if dynamic_success_callbacks is None:
            return list(global_callbacks)
        return list(set(dynamic_success_callbacks + global_callbacks))

    def _remove_internal_litellm_callbacks(self, callbacks: List) -> List:
        return callbacks

    def _get_callback_name(self, cb) -> str:
        if isinstance(cb, str):
            return cb
        if hasattr(cb, "__name__"):
            return cb.__name__
        if hasattr(cb, "__func__"):
            return cb.__func__.__name__
        if hasattr(cb, "__class__"):
            return cb.__class__.__name__
        return str(cb)

    def _is_internal_litellm_proxy_callback(self, cb) -> bool:
        return False

    def _remove_internal_custom_logger_callbacks(self, callbacks: List) -> List:
        return callbacks

    def _get_assembled_streaming_response(
        self,
        result: Union[
            ModelResponse,
            TextCompletionResponse,
            ModelResponseStream,
            ResponseCompletedEvent,
            Any,
        ],
        start_time: datetime.datetime,
        end_time: datetime.datetime,
        is_async: bool,
        streaming_chunks: List[Any],
    ) -> Optional[Union[ModelResponse, TextCompletionResponse, ResponsesAPIResponse]]:
        return None

    def _handle_anthropic_messages_response_logging(
        self, result: Any
    ) -> Union[ModelResponse, ResponsesAPIResponse]:
        return result

    def _handle_non_streaming_google_genai_generate_content_response_logging(self, result: Any) -> ModelResponse:
        return result

    def _handle_a2a_response_logging(self, result: Any) -> Any:
        return result

def _get_masked_values(
    sensitive_object: dict,
    ignore_sensitive_values: bool = False,
    mask_all_values: bool = False,
    unmasked_length: int = 4,
    number_of_asterisks: Optional[int] = 4,
    _depth: int = 0,
    _max_depth: int = 20,
) -> dict:
    sensitive_keywords = [
        "authorization",
        "token",
        "key",
        "secret",
        "vertex_credentials",
        "credentials",
        "password",
        "passwd",
    ]

    def _mask_value(v: Any) -> Any:
        if isinstance(v, dict):
            if _depth >= _max_depth:
                return v
            return _get_masked_values(
                v,
                ignore_sensitive_values=ignore_sensitive_values,
                mask_all_values=mask_all_values,
                unmasked_length=unmasked_length,
                number_of_asterisks=number_of_asterisks,
                _depth=_depth + 1,
                _max_depth=_max_depth,
            )
        if not isinstance(v, str):
            return v
        if len(v) <= unmasked_length:
            return "*****"
        if number_of_asterisks is not None:
            return (
                v[: unmasked_length // 2]
                + "*" * number_of_asterisks
                + v[-unmasked_length // 2 :]
            )
        return (
            v[: unmasked_length // 2]
            + "*" * (len(v) - unmasked_length)
            + v[-unmasked_length // 2 :]
        )

    return {
        k: (
            v
            if ignore_sensitive_values
            or not any(
                sensitive_keyword in k.lower()
                for sensitive_keyword in sensitive_keywords
            )
            else _mask_value(v)
        )
        for k, v in sensitive_object.items()
    }

def is_valid_sha256_hash(value: str) -> bool:
    # Check if the value is a valid SHA-256 hash (64 hexadecimal characters)
    return bool(re.fullmatch(r"[a-fA-F0-9]{64}", value))


class StandardLoggingPayloadSetup:
    @staticmethod
    def cleanup_timestamps(
        start_time: Union[dt_object, float],
        end_time: Union[dt_object, float],
        completion_start_time: Union[dt_object, float],
    ) -> Tuple[float, float, float]:
        return start_time_float, end_time_float, completion_start_time_float

    @staticmethod
    def append_system_prompt_messages(kwargs: Optional[Dict] = None, messages: Optional[Any] = None):
        return messages

    @staticmethod
    def merge_litellm_metadata(litellm_params: dict) -> dict:
        return {}

    @staticmethod
    def get_standard_logging_metadata(
        metadata: Optional[Dict[str, Any]],
        litellm_params: Optional[dict] = None,
        prompt_integration: Optional[str] = None,
        applied_guardrails: Optional[List[str]] = None,
        mcp_tool_call_metadata: Optional[StandardLoggingMCPToolCall] = None,
        vector_store_request_metadata: Optional[
            List[StandardLoggingVectorStoreRequest]
        ] = None,
        usage_object: Optional[dict] = None,
        proxy_server_request: Optional[dict] = None,
        start_time: Optional[dt_object] = None,
        response_id: Optional[str] = None,
    ) -> StandardLoggingMetadata:
        """
        Clean and filter the metadata dictionary to include only the specified keys in StandardLoggingMetadata.

        Args:
            metadata (Optional[Dict[str, Any]]): The original metadata dictionary.

        Returns:
            StandardLoggingMetadata: A StandardLoggingMetadata object containing the cleaned metadata.

        Note:
            - If the input metadata is None or not a dictionary, an empty StandardLoggingMetadata object is returned.
            - If 'user_api_key' is present in metadata and is a valid SHA256 hash, it's stored as 'user_api_key_hash'.
        """

        prompt_management_metadata: Optional[
            StandardLoggingPromptManagementMetadata
        ] = None

        if litellm_params is not None:
            prompt_id = cast(Optional[str], litellm_params.get("prompt_id", None))
            prompt_variables = cast(
                Optional[dict], litellm_params.get("prompt_variables", None)
            )

            if prompt_id is not None and prompt_integration is not None:
                prompt_management_metadata = StandardLoggingPromptManagementMetadata(
                    prompt_id=prompt_id,
                    prompt_variables=prompt_variables,
                    prompt_integration=prompt_integration,
                )

        # Initialize with default values
        clean_metadata = StandardLoggingMetadata(
            user_api_key_hash=None,
            user_api_key_alias=None,
            user_api_key_spend=None,
            user_api_key_max_budget=None,
            user_api_key_budget_reset_at=None,
            user_api_key_team_id=None,
            user_api_key_org_id=None,
            user_api_key_org_alias=None,
            user_api_key_project_id=None,
            user_api_key_project_alias=None,
            user_api_key_user_id=None,
            user_api_key_team_alias=None,
            user_api_key_user_email=None,
            user_api_key_end_user_id=None,
            user_api_key_request_route=None,
            spend_logs_metadata=None,
            requester_ip_address=None,
            user_agent=None,
            requester_metadata=None,
            prompt_management_metadata=prompt_management_metadata,
            applied_guardrails=applied_guardrails,
            mcp_tool_call_metadata=mcp_tool_call_metadata,
            vector_store_request_metadata=vector_store_request_metadata,
            usage_object=usage_object,
            requester_custom_headers=None,
            cold_storage_object_key=None,
            user_api_key_auth_metadata=None,
            team_alias=None,
            team_id=None,
        )
        if isinstance(metadata, dict):
            for key in metadata.keys() & _STANDARD_LOGGING_METADATA_KEYS:
                clean_metadata[key] = metadata[key]  # type: ignore

            user_api_key = metadata.get("user_api_key")
            if (
                user_api_key
                and isinstance(user_api_key, str)
                and is_valid_sha256_hash(user_api_key)
            ):
                clean_metadata["user_api_key_hash"] = user_api_key
            _potential_requester_metadata = metadata.get(
                "metadata", None
            )  # check if user passed metadata in the sdk request - e.g. metadata for langsmith logging - https://docs.litellm.ai/docs/observability/langsmith_integration#set-langsmith-fields
            if (
                clean_metadata["requester_metadata"] is None
                and _potential_requester_metadata is not None
                and isinstance(_potential_requester_metadata, dict)
            ):
                clean_metadata["requester_metadata"] = _potential_requester_metadata

        if (
            EnterpriseStandardLoggingPayloadSetupVAR
            and proxy_server_request is not None
        ):
            clean_metadata = EnterpriseStandardLoggingPayloadSetupVAR.apply_enterprise_specific_metadata(
                standard_logging_metadata=clean_metadata,
                proxy_server_request=proxy_server_request,
            )

        # Generate cold storage object key if cold storage is configured
        if start_time is not None and response_id is not None:
            cold_storage_object_key = (
                StandardLoggingPayloadSetup._generate_cold_storage_object_key(
                    start_time=start_time,
                    response_id=response_id,
                    team_alias=clean_metadata.get("user_api_key_team_alias"),
                )
            )
            if cold_storage_object_key:
                clean_metadata["cold_storage_object_key"] = cold_storage_object_key

        return clean_metadata

    @staticmethod
    def get_usage_from_response_obj(
        response_obj: Optional[dict], combined_usage_object: Optional[Usage] = None
    ) -> Usage:
        return Usage(
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
        )

    @staticmethod
    def get_usage_as_dict(
        response_obj: Optional[dict],
        combined_usage_object: Optional[Usage] = None,
    ) -> dict:
        _empty: dict = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        return _empty

    @staticmethod
    def get_model_cost_information(
        base_model: Optional[str],
        custom_pricing: Optional[bool],
        custom_llm_provider: Optional[str],
        init_response_obj: Union[Any, BaseModel, dict],
        api_base: Optional[str] = None,
    ) -> StandardLoggingModelInformation:
        model_cost_information = StandardLoggingModelInformation(model_map_key="", model_map_value=None)
        return model_cost_information

    @staticmethod
    def get_final_response_obj(
        response_obj: dict, init_response_obj: Union[Any, BaseModel, dict], kwargs: dict
    ) -> Optional[Union[dict, str, list]]:
        return {}

    @staticmethod
    def get_additional_headers(
        additiona_headers: Optional[dict],
    ) -> Optional[StandardLoggingAdditionalHeaders]:
        return None

    @staticmethod
    def get_hidden_params(
        hidden_params: Optional[dict],
    ) -> StandardLoggingHiddenParams:
        clean_hidden_params = StandardLoggingHiddenParams(
            model_id=None,
            cache_key=None,
            api_base=None,
            response_cost=None,
            additional_headers=None,
            litellm_overhead_time_ms=None,
            batch_models=None,
            litellm_model_name=None,
            usage_object=None,
        )
        return clean_hidden_params

    @staticmethod
    def strip_trailing_slash(api_base: Optional[str]) -> Optional[str]:
        if api_base:
            if api_base.endswith("//"):
                return api_base.rstrip("/")
            if api_base[-1] == "/":
                return api_base[:-1]
        return api_base

    @staticmethod
    def _generate_cold_storage_object_key(
        start_time: dt_object,
        response_id: str,
        team_alias: Optional[str] = None,
    ) -> Optional[str]:
        return None

    @staticmethod
    def get_error_information(
        original_exception: Optional[Exception],
        traceback_str: Optional[str] = None,
    ) -> StandardLoggingPayloadErrorInformation:
        from litellm.constants import MAXIMUM_TRACEBACK_LINES_TO_LOG

        # ProxyException uses .code, LiteLLM exceptions use .status_code,
        # httpx.HTTPStatusError exposes status only as .response.status_code.
        # Stringified for Prisma JSON compatibility.
        error_code_attr = getattr(original_exception, "code", None)
        if error_code_attr is not None and str(error_code_attr) not in ("", "None"):
            error_status: str = str(error_code_attr)
        else:
            status_code_attr = getattr(original_exception, "status_code", None)
            if status_code_attr is None:
                response_attr = getattr(original_exception, "response", None)
                status_code_attr = getattr(response_attr, "status_code", None)
            error_status = str(status_code_attr) if status_code_attr is not None else ""
        error_class: str = (
            str(original_exception.__class__.__name__) if original_exception else ""
        )
        _llm_provider_in_exception = getattr(original_exception, "llm_provider", "")

        # Get traceback information (first 100 lines)
        traceback_info = traceback_str or ""
        if original_exception:
            tb = getattr(original_exception, "__traceback__", None)
            if tb:
                tb_lines = traceback.format_tb(tb)
                traceback_info += "".join(
                    tb_lines[:MAXIMUM_TRACEBACK_LINES_TO_LOG]
                )  # Limit to first 100 lines

        explicit_message = getattr(original_exception, "message", None)
        error_message = (
            explicit_message
            if isinstance(explicit_message, str) and explicit_message
            else str(original_exception)
        )

        return StandardLoggingPayloadErrorInformation(
            error_code=error_status,
            error_class=error_class,
            llm_provider=_llm_provider_in_exception,
            traceback=traceback_info,
            error_message=error_message if original_exception else "",
        )

    @staticmethod
    def get_response_time(
        start_time_float: float,
        end_time_float: float,
        completion_start_time_float: float,
        stream: bool,
    ) -> float:
        """
        Get the response time for the LLM response

        Args:
            start_time_float: float - start time of the LLM call
            end_time_float: float - end time of the LLM call
            completion_start_time_float: float - time to first token of the LLM response (for streaming responses)
            stream: bool - True when a stream response is returned

        Returns:
            float: The response time for the LLM response
        """
        if stream is True:
            return completion_start_time_float - start_time_float
        else:
            return end_time_float - start_time_float

    @staticmethod
    def _get_standard_logging_payload_trace_id(
        logging_obj: Logging,
        litellm_params: dict,
    ) -> str:
        """
        Returns the `litellm_trace_id` for this request

        This helps link sessions when multiple requests are made in a single session
        """
        dynamic_litellm_session_id = litellm_params.get("litellm_session_id")
        dynamic_litellm_trace_id = litellm_params.get("litellm_trace_id")

        # Note: we recommend using `litellm_session_id` for session tracking
        # `litellm_trace_id` is an internal litellm param
        if dynamic_litellm_session_id:
            return str(dynamic_litellm_session_id)
        elif dynamic_litellm_trace_id:
            return str(dynamic_litellm_trace_id)
        # Fallback: use metadata.session_id or metadata.trace_id for call chaining
        metadata = litellm_params.get("metadata") or {}
        metadata_session_id = metadata.get("session_id")
        metadata_trace_id = metadata.get("trace_id")
        if metadata_session_id:
            return str(metadata_session_id)
        if metadata_trace_id:
            return str(metadata_trace_id)
        return logging_obj.litellm_trace_id

    @staticmethod
    def _get_user_agent_tags(proxy_server_request: dict) -> Optional[List[str]]:
        """
        Return the user agent tags from the proxy server request for spend tracking
        """
        if litellm.disable_add_user_agent_to_request_tags is True:
            return None
        user_agent_tags: Optional[List[str]] = None
        headers = proxy_server_request.get("headers", {})
        if headers is not None and isinstance(headers, dict):
            if "user-agent" in headers:
                user_agent = headers["user-agent"]
                if user_agent is not None:
                    if user_agent_tags is None:
                        user_agent_tags = []
                    user_agent_part: Optional[str] = None
                    if "/" in user_agent:
                        user_agent_part = user_agent.split("/")[0]
                    if user_agent_part is not None:
                        user_agent_tags.append("User-Agent: " + user_agent_part)
                    if user_agent is not None:
                        user_agent_tags.append("User-Agent: " + user_agent)
        return user_agent_tags

    @staticmethod
    def _get_extra_header_tags(proxy_server_request: dict) -> Optional[List[str]]:
        """
        Extract additional header tags for spend tracking based on config.
        """
        extra_headers: List[str] = (
            getattr(litellm, "extra_spend_tag_headers", None) or []
        )
        if not extra_headers:
            return None

        headers = proxy_server_request.get("headers", {})
        if not isinstance(headers, dict):
            return None

        header_tags = []
        for header_name in extra_headers:
            header_value = headers.get(header_name)
            if header_value:
                header_tags.append(f"{header_name}: {header_value}")

        return header_tags if header_tags else None

    @staticmethod
    def _get_request_tags(
        litellm_params: dict, proxy_server_request: dict
    ) -> List[str]:
        # check for 'tags' in both 'metadata' and 'litellm_metadata'
        metadata = litellm_params.get("metadata") or {}
        litellm_metadata = litellm_params.get("litellm_metadata") or {}
        if metadata.get("tags", []):
            request_tags = metadata.get("tags", []).copy()
        elif litellm_metadata.get("tags", []):
            request_tags = litellm_metadata.get("tags", []).copy()
        else:
            request_tags = []
        user_agent_tags = StandardLoggingPayloadSetup._get_user_agent_tags(
            proxy_server_request
        )
        additional_header_tags = StandardLoggingPayloadSetup._get_extra_header_tags(
            proxy_server_request
        )
        if user_agent_tags is not None:
            request_tags.extend(user_agent_tags)
        if additional_header_tags is not None:
            request_tags.extend(additional_header_tags)
        return request_tags


def _get_status_fields(
    status: StandardLoggingPayloadStatus,
    guardrail_information: Optional[List[dict]],
    error_str: Optional[str],
) -> "StandardLoggingPayloadStatusFields":
    """
    Determine status fields based on request status and guardrail information.

    Args:
        status: Overall request status ("success" or "failure")
        guardrail_information: Guardrail information from metadata
        error_str: Error string if any

    Returns:
        StandardLoggingPayloadStatusFields with llm_api_status and guardrail_status
    """
    # Mapping for legacy guardrail status values to new GuardrailStatus values
    GUARDRAIL_STATUS_MAP: Dict[str, GuardrailStatus] = {
        "success": "success",
        "blocked": "guardrail_intervened",  # legacy
        "guardrail_intervened": "guardrail_intervened",  # direct
        "failure": "guardrail_failed_to_respond",  # legacy
        "guardrail_failed_to_respond": "guardrail_failed_to_respond",  # direct
        "not_run": "not_run",
    }

    # Set LLM API status
    llm_api_status: StandardLoggingPayloadStatus = status

    #########################################################
    # Map - guardrail_information.guardrail_status to guardrail_status
    #########################################################
    guardrail_status: GuardrailStatus = "not_run"
    if guardrail_information and isinstance(guardrail_information, list):
        for information in guardrail_information:
            if isinstance(information, dict):
                raw_status = information.get("guardrail_status", "not_run")
                if raw_status != "not_run":
                    guardrail_status = GUARDRAIL_STATUS_MAP.get(raw_status, "not_run")
                    break

    return StandardLoggingPayloadStatusFields(
        llm_api_status=llm_api_status, guardrail_status=guardrail_status
    )


def _extract_response_obj_and_hidden_params(
    init_response_obj: Union[Any, BaseModel, dict],
    original_exception: Optional[Exception],
) -> Tuple[dict, Optional[dict]]:
    """Extract response_obj and hidden_params from init_response_obj."""
    hidden_params: Optional[dict] = None
    if init_response_obj is None:
        response_obj = {}
    elif isinstance(init_response_obj, BaseModel):
        response_obj = init_response_obj.model_dump()
        hidden_params = getattr(init_response_obj, "_hidden_params", None)
    elif isinstance(init_response_obj, dict):
        response_obj = init_response_obj
    else:
        response_obj = {}

    if original_exception is not None and hidden_params is None:
        response_headers = _get_response_headers(original_exception)
        if response_headers is not None:
            hidden_params = dict(
                StandardLoggingHiddenParams(
                    additional_headers=StandardLoggingPayloadSetup.get_additional_headers(
                        dict(response_headers)
                    ),
                    model_id=None,
                    cache_key=None,
                    api_base=None,
                    response_cost=None,
                    litellm_overhead_time_ms=None,
                    batch_models=None,
                    litellm_model_name=None,
                    usage_object=None,
                )
            )

    return response_obj, hidden_params


def get_standard_logging_object_payload(
    kwargs: Optional[dict],
    init_response_obj: Union[Any, BaseModel, dict],
    start_time: dt_object,
    end_time: dt_object,
    logging_obj: Logging,
    status: StandardLoggingPayloadStatus,
    error_str: Optional[str] = None,
    original_exception: Optional[Exception] = None,
    standard_built_in_tools_params: Optional[StandardBuiltInToolsParams] = None,
) -> Optional[StandardLoggingPayload]:
    try:
        kwargs = kwargs or {}

        response_obj, hidden_params = _extract_response_obj_and_hidden_params(
            init_response_obj, original_exception
        )

        # standardize this function to be used across, s3, dynamoDB, langfuse logging
        litellm_params = kwargs.get("litellm_params", {}) or {}
        proxy_server_request = litellm_params.get("proxy_server_request") or {}

        # Merge both litellm_metadata and metadata to get complete metadata
        metadata: dict = StandardLoggingPayloadSetup.merge_litellm_metadata(
            litellm_params
        )

        completion_start_time = kwargs.get("completion_start_time", end_time)
        call_type = kwargs.get("call_type")
        cache_hit = kwargs.get("cache_hit", False)
        # Extract usage as a plain dict, avoiding Pydantic round-trip
        usage_dict = StandardLoggingPayloadSetup.get_usage_as_dict(
            response_obj=response_obj,
            combined_usage_object=cast(
                Optional[Usage], kwargs.get("combined_usage_object")
            ),
        )

        id = response_obj.get("id", kwargs.get("litellm_call_id"))

        _model_id = metadata.get("model_info", {}).get("id", "")
        _model_group = metadata.get("model_group", "")

        request_tags = StandardLoggingPayloadSetup._get_request_tags(
            litellm_params=litellm_params, proxy_server_request=proxy_server_request
        )

        # cleanup timestamps
        (
            start_time_float,
            end_time_float,
            completion_start_time_float,
        ) = StandardLoggingPayloadSetup.cleanup_timestamps(
            start_time=start_time,
            end_time=end_time,
            completion_start_time=completion_start_time,
        )
        response_time = StandardLoggingPayloadSetup.get_response_time(
            start_time_float=start_time_float,
            end_time_float=end_time_float,
            completion_start_time_float=completion_start_time_float,
            stream=kwargs.get("stream", False),
        )
        # clean up litellm metadata
        clean_metadata = StandardLoggingPayloadSetup.get_standard_logging_metadata(
            metadata=metadata,
            litellm_params=litellm_params,
            prompt_integration=kwargs.get("prompt_integration", None),
            applied_guardrails=kwargs.get("applied_guardrails", None),
            mcp_tool_call_metadata=kwargs.get("mcp_tool_call_metadata", None),
            vector_store_request_metadata=kwargs.get(
                "vector_store_request_metadata", None
            ),
            usage_object=usage_dict,
            proxy_server_request=proxy_server_request,
            start_time=start_time,
            response_id=id,
        )
        _request_body = proxy_server_request.get("body", {})
        end_user_id = clean_metadata["user_api_key_end_user_id"] or _request_body.get(
            "user", None
        )  # maintain backwards compatibility with old request body check

        saved_cache_cost: float = 0.0
        if cache_hit is True:
            id = f"{id}_cache_hit{time.time()}"  # do not duplicate the request id
            saved_cache_cost = (
                logging_obj._response_cost_calculator(
                    result=init_response_obj, cache_hit=False  # type: ignore
                )
                or 0.0
            )

        ## Get model cost information ##
        base_model = _get_base_model_from_metadata(model_call_details=kwargs)
        custom_pricing = False
        raw_response_cost = kwargs.get("response_cost")
        response_cost: float = raw_response_cost or 0.0

        # clean up litellm hidden params
        clean_hidden_params = StandardLoggingPayloadSetup.get_hidden_params(
            hidden_params
        )
        if (
            clean_hidden_params["response_cost"] is None
            and raw_response_cost is not None
        ):
            clean_hidden_params["response_cost"] = response_cost

        model_cost_information = StandardLoggingPayloadSetup.get_model_cost_information(
            base_model=base_model,
            custom_pricing=custom_pricing,
            custom_llm_provider=kwargs.get("custom_llm_provider"),
            init_response_obj=init_response_obj,
            api_base=litellm_params.get("api_base"),
        )

        error_information = StandardLoggingPayloadSetup.get_error_information(
            original_exception=original_exception,
        )

        ## get final response object ##
        final_response_obj = StandardLoggingPayloadSetup.get_final_response_obj(
            response_obj=response_obj,
            init_response_obj=init_response_obj,
            kwargs=kwargs,
        )

        stream: Optional[bool] = None
        if (
            kwargs.get("complete_streaming_response") is not None
            or kwargs.get("async_complete_streaming_response") is not None
        ) and kwargs.get("stream") is True:
            stream = True

        # Reconstruct full model name with provider prefix for logging
        # This ensures Bedrock models like "us.anthropic.claude-3-5-sonnet-20240620-v1:0"
        # are logged as "bedrock/us.anthropic.claude-3-5-sonnet-20240620-v1:0"
        custom_llm_provider = cast(Optional[str], kwargs.get("custom_llm_provider"))
        model_name = kwargs.get("model", "") or ""
        response_model_name: Optional[str] = None
        if isinstance(final_response_obj, dict):
            response_model_name = final_response_obj.get("model")

        # For Azure Model Router, preserve the actual model in the top-level standard
        # logging payload only when the user has opted in.
        requested_model = kwargs.get("model")
        if (
            isinstance(requested_model, str)
            and (
                "model_router" in requested_model.lower()
                or "model-router" in requested_model.lower()
            )
            and isinstance(response_model_name, str)
            and response_model_name
        ):
            model_name = response_model_name

        payload: StandardLoggingPayload = StandardLoggingPayload(
            id=str(id),
            litellm_call_id=kwargs.get("litellm_call_id")
            or litellm_params.get("litellm_call_id"),
            trace_id=StandardLoggingPayloadSetup._get_standard_logging_payload_trace_id(
                logging_obj=logging_obj,
                litellm_params=litellm_params,
            ),
            call_type=call_type or "",
            cache_hit=cache_hit,
            stream=stream,
            status=status,
            status_fields=_get_status_fields(
                status=status,
                guardrail_information=metadata.get(
                    "standard_logging_guardrail_information", None
                ),
                error_str=error_str,
            ),
            custom_llm_provider=custom_llm_provider,
            saved_cache_cost=saved_cache_cost,
            startTime=start_time_float,
            endTime=end_time_float,
            completionStartTime=completion_start_time_float,
            response_time=response_time,
            model=model_name,
            metadata=clean_metadata,
            cache_key=clean_hidden_params["cache_key"],
            response_cost=response_cost,
            cost_breakdown=logging_obj.cost_breakdown,
            total_tokens=usage_dict.get("total_tokens", 0),
            prompt_tokens=usage_dict.get("prompt_tokens", 0),
            completion_tokens=usage_dict.get("completion_tokens", 0),
            request_tags=request_tags,
            end_user=end_user_id or "",
            api_base=StandardLoggingPayloadSetup.strip_trailing_slash(
                litellm_params.get("api_base", "")
            )
            or "",
            model_group=_model_group,
            model_id=_model_id,
            requester_ip_address=clean_metadata.get("requester_ip_address", None),
            user_agent=clean_metadata.get("user_agent", None),
            messages=kwargs.get("messages"),
            response=final_response_obj,
            model_parameters={},
            hidden_params=clean_hidden_params,
            model_map_information=model_cost_information,
            error_str=error_str,
            error_information=error_information,
            response_cost_failure_debug_info=kwargs.get(
                "response_cost_failure_debug_information"
            ),
            guardrail_information=metadata.get(
                "standard_logging_guardrail_information", None
            ),
            standard_built_in_tools_params=standard_built_in_tools_params,
        )

        # emit_standard_logging_payload(payload) - Moved to success_handler to prevent double emitting

        return payload
    except Exception as e:
        log.exception("Error creating standard logging object - {}".format(str(e)))
        return None


def emit_standard_logging_payload(payload: StandardLoggingPayload):
    if os.getenv("LITELLM_PRINT_STANDARD_LOGGING_PAYLOAD"):
        print(json.dumps(payload, indent=4))  # noqa


def get_standard_logging_metadata(
    metadata: Optional[Dict[str, Any]],
) -> StandardLoggingMetadata:
    """
    Clean and filter the metadata dictionary to include only the specified keys in StandardLoggingMetadata.

    Args:
        metadata (Optional[Dict[str, Any]]): The original metadata dictionary.

    Returns:
        StandardLoggingMetadata: A StandardLoggingMetadata object containing the cleaned metadata.

    Note:
        - If the input metadata is None or not a dictionary, an empty StandardLoggingMetadata object is returned.
        - If 'user_api_key' is present in metadata and is a valid SHA256 hash, it's stored as 'user_api_key_hash'.
    """
    # Initialize with default values
    clean_metadata = StandardLoggingMetadata(
        user_api_key_hash=None,
        user_api_key_alias=None,
        user_api_key_spend=None,
        user_api_key_max_budget=None,
        user_api_key_budget_reset_at=None,
        user_api_key_team_id=None,
        user_api_key_org_id=None,
        user_api_key_org_alias=None,
        user_api_key_project_id=None,
        user_api_key_project_alias=None,
        user_api_key_user_id=None,
        user_api_key_user_email=None,
        user_api_key_team_alias=None,
        spend_logs_metadata=None,
        requester_ip_address=None,
        user_agent=None,
        requester_metadata=None,
        user_api_key_end_user_id=None,
        prompt_management_metadata=None,
        applied_guardrails=None,
        mcp_tool_call_metadata=None,
        vector_store_request_metadata=None,
        usage_object=None,
        requester_custom_headers=None,
        user_api_key_request_route=None,
        cold_storage_object_key=None,
        user_api_key_auth_metadata=None,
        team_alias=None,
        team_id=None,
    )
    if isinstance(metadata, dict):
        # Update the clean_metadata with values from input metadata that match StandardLoggingMetadata fields
        for key in StandardLoggingMetadata.__annotations__.keys():
            if key in metadata:
                clean_metadata[key] = metadata[key]  # type: ignore

        if metadata.get("user_api_key") is not None:
            if is_valid_sha256_hash(str(metadata.get("user_api_key"))):
                clean_metadata["user_api_key_hash"] = metadata.get(
                    "user_api_key"
                )  # this is the hash
    return clean_metadata


def scrub_sensitive_keys_in_metadata(litellm_params: Optional[dict]):
    if litellm_params is None:
        litellm_params = {}

    metadata = litellm_params.get("metadata", {}) or {}

    ## Extract provider-specific callable values (like langfuse_masking_function)
    ## Store them separately so only the intended logger can access them
    ## This prevents callables from leaking to other logging integrations
    if "langfuse_masking_function" in metadata:
        masking_fn = metadata.pop("langfuse_masking_function", None)
        if callable(masking_fn):
            litellm_params["_langfuse_masking_function"] = masking_fn
        litellm_params["metadata"] = metadata

    ## check user_api_key_metadata for sensitive logging keys
    cleaned_user_api_key_metadata = {}
    if "user_api_key_metadata" in metadata and isinstance(
        metadata["user_api_key_metadata"], dict
    ):
        for k, v in metadata["user_api_key_metadata"].items():
            if k == "logging":  # prevent logging user logging keys
                cleaned_user_api_key_metadata[k] = (
                    "scrubbed_by_litellm_for_sensitive_keys"
                )
            else:
                cleaned_user_api_key_metadata[k] = v

        metadata["user_api_key_metadata"] = cleaned_user_api_key_metadata
        litellm_params["metadata"] = metadata

    return litellm_params


# integration helper function
def modify_integration(integration_name, integration_params):
    global supabaseClient
    if integration_name == "supabase":
        if "table_name" in integration_params:
            Supabase.supabase_table_name = integration_params["table_name"]


@lru_cache(maxsize=16)
def _get_traceback_str_for_error(error_str: str) -> str:
    """
    function wrapped with lru_cache to limit the number of times `traceback.format_exc()` is called
    """
    return traceback.format_exc()


from decimal import Decimal

# used for unit testing
from typing import Any, Dict, List, Optional, Union


def create_dummy_standard_logging_payload() -> StandardLoggingPayload:
    # First create the nested objects with proper typing
    model_info = StandardLoggingModelInformation(
        model_map_key="gpt-3.5-turbo", model_map_value=None
    )

    metadata = StandardLoggingMetadata(  # type: ignore
        user_api_key_hash=str("test_hash"),
        user_api_key_alias=str("test_alias"),
        user_api_key_team_id=str("test_team"),
        user_api_key_user_id=str("test_user"),
        user_api_key_team_alias=str("test_team_alias"),
        user_api_key_org_id=None,
        spend_logs_metadata=None,
        requester_ip_address=str("127.0.0.1"),
        requester_metadata=None,
        user_api_key_end_user_id=str("test_end_user"),
    )

    hidden_params = StandardLoggingHiddenParams(
        model_id=None,
        cache_key=None,
        api_base=None,
        response_cost=None,
        additional_headers=None,
        litellm_overhead_time_ms=None,
        batch_models=None,
        litellm_model_name=None,
        usage_object=None,
    )

    # Convert numeric values to appropriate types
    response_cost = Decimal("0.1")
    start_time = Decimal("1234567890.0")
    end_time = Decimal("1234567891.0")
    completion_start_time = Decimal("1234567890.5")
    saved_cache_cost = Decimal("0.0")

    # Create messages and response with proper typing
    messages: List[Dict[str, str]] = [{"role": "user", "content": "Hello, world!"}]
    response: Dict[str, List[Dict[str, Dict[str, str]]]] = {
        "choices": [{"message": {"content": "Hi there!"}}]
    }

    # Main payload initialization
    return StandardLoggingPayload(  # type: ignore
        id=str("test_id"),
        call_type=str("completion"),
        stream=bool(False),
        response_cost=response_cost,
        response_cost_failure_debug_info=None,
        status=str("success"),
        total_tokens=int(
            DEFAULT_MOCK_RESPONSE_PROMPT_TOKEN_COUNT
            + DEFAULT_MOCK_RESPONSE_COMPLETION_TOKEN_COUNT
        ),
        prompt_tokens=int(DEFAULT_MOCK_RESPONSE_PROMPT_TOKEN_COUNT),
        completion_tokens=int(DEFAULT_MOCK_RESPONSE_COMPLETION_TOKEN_COUNT),
        startTime=start_time,
        endTime=end_time,
        completionStartTime=completion_start_time,
        model_map_information=model_info,
        model=str("gpt-3.5-turbo"),
        model_id=str("model-123"),
        model_group=str("openai-gpt"),
        custom_llm_provider=str("openai"),
        api_base=str("https://api.openai.com"),
        metadata=metadata,
        cache_hit=bool(False),
        cache_key=None,
        saved_cache_cost=saved_cache_cost,
        request_tags=[],
        end_user=None,
        requester_ip_address=str("127.0.0.1"),
        messages=messages,
        response=response,
        error_str=None,
        model_parameters={"stream": True},
        hidden_params=hidden_params,
    )
