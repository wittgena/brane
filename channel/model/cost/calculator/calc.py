# channel.model.cost.calculator.calc
## @lineage: channel.cost.calc
import time
from typing import TYPE_CHECKING, Any, List, Literal, Optional, Tuple, Union, cast
from httpx import Response
from pydantic import BaseModel
from functools import lru_cache

from bound.config.resolver import config
from channel.model.token.counter import token_counter

from channel.model.provider.gate import _get_model_info_helper
from channel.model.cost.map import model_cost
from bound.config.constants import (
    DEFAULT_MAX_LRU_CACHE_SIZE,
    DEFAULT_REPLICATE_GPU_PRICE_PER_SECOND,
)
from channel.model.cost.track.toolcall import StandardBuiltInToolCostTracking
from channel.model.cost.calculator.transform import TranscriptionUsageObjectTransformation
from channel.model.cost.calculator.utils import (
    CostCalculatorUtils,
    _generic_cost_per_character,
    _get_regional_uplift_multiplier,
    _get_service_tier_cost_key,
    _parse_prompt_tokens_details,
    calculate_cost_component,
    generic_cost_per_token,
    get_billable_input_tokens,
    select_cost_metric_for_model,
)
from channel.model.provider.resolver import get_llm_provider
from channel.bridge.llms.anthropic.cost_calculation import cost_per_token as anthropic_cost_per_token
from channel.bridge.llms.google_genai.cost_calculator import cost_per_token as gemini_cost_per_token
from channel.bridge.llms.openai.cost_calculation import cost_per_token as openai_cost_per_token
from channel.model.types.llms.openai import (
    HttpxBinaryResponseContent,
    OpenAIModerationResponse,
    OpenAIRealtimeStreamList,
    OpenAIRealtimeStreamResponseBaseObject,
    OpenAIRealtimeStreamSessionEvents,
    ResponseAPIUsage,
    ResponsesAPIResponse,
)
from channel.model.types.rerank import RerankBilledUnits, RerankResponse
from channel.model.types.utils import CallTypesLiteral, LiteLLMRealtimeStreamLoggingObject, LlmProvidersSet, StandardBuiltInToolsParams, Usage
from channel.model.types.utils import CallTypes, CostPerToken, EmbeddingResponse, ImageResponse, TextCompletionResponse, TranscriptionResponse

from anchor.router.switch.params import ModelResponse, ModelResponseStream
from watcher.plane.emitter import get_emitter

log = get_emitter("cost.calculator")

LitellmLoggingObject = Any

# Pre-resolved CallTypes enum values for fast membership checks
_A2A_CALL_TYPES = frozenset(
    {
        CallTypes.asend_message.value,
        CallTypes.send_message.value,
    }
)

_VIDEO_CALL_TYPES = frozenset(
    {
        CallTypes.create_video.value,
        CallTypes.acreate_video.value,
        CallTypes.video_edit.value,
        CallTypes.avideo_edit.value,
        CallTypes.video_remix.value,
        CallTypes.avideo_remix.value,
    }
)

_SPEECH_CALL_TYPES = frozenset(
    {
        CallTypes.speech.value,
        CallTypes.aspeech.value,
    }
)

_TRANSCRIPTION_CALL_TYPES = frozenset(
    {
        CallTypes.atranscription.value,
        CallTypes.transcription.value,
    }
)

_RERANK_CALL_TYPES = frozenset(
    {
        CallTypes.rerank.value,
        CallTypes.arerank.value,
    }
)

_SEARCH_CALL_TYPES = frozenset(
    {
        CallTypes.search.value,
        CallTypes.asearch.value,
    }
)

_AREALTIME_CALL_TYPE = CallTypes.arealtime.value
_MCP_CALL_TYPE = CallTypes.call_mcp_tool.value

def _cost_per_token_custom_pricing_helper(
    prompt_tokens: float = 0,
    completion_tokens: float = 0,
    response_time_ms: Optional[float] = 0.0,
    cached_tokens: float = 0,
    cache_creation_tokens: float = 0,
    ### CUSTOM PRICING ###
    custom_cost_per_token: Optional[CostPerToken] = None,
    custom_cost_per_second: Optional[float] = None,
) -> Optional[Tuple[float, float]]:
    """Internal helper function for calculating cost, if custom pricing given.

    prompt_tokens is assumed to include both cached_tokens and cache_creation_tokens
    (OpenAI-compatible convention). Anthropic-style usage where prompt_tokens excludes
    cache tokens is handled at the caller (cost_per_token) before invoking this helper.
    """
    if custom_cost_per_token is None and custom_cost_per_second is None:
        return None

    if custom_cost_per_token is not None:
        input_cost_per_token = custom_cost_per_token["input_cost_per_token"]
        output_cost_per_token = custom_cost_per_token["output_cost_per_token"]

        cache_read_input_token_cost = custom_cost_per_token.get(
            "cache_read_input_token_cost",
            input_cost_per_token,
        )
        cache_creation_input_token_cost = custom_cost_per_token.get(
            "cache_creation_input_token_cost",
            input_cost_per_token,
        )

        regular_prompt_tokens = max(
            prompt_tokens - cached_tokens - cache_creation_tokens,
            0,
        )

        input_cost = (
            regular_prompt_tokens * input_cost_per_token
            + cached_tokens * cache_read_input_token_cost
            + cache_creation_tokens * cache_creation_input_token_cost
        )
        output_cost = completion_tokens * output_cost_per_token
        return input_cost, output_cost
    elif custom_cost_per_second is not None:
        output_cost = custom_cost_per_second * response_time_ms / 1000  # type: ignore
        return 0, output_cost

    return None


def _get_additional_costs(
    model: str,
    custom_llm_provider: Optional[str],
    prompt_tokens: int,
    completion_tokens: int,
) -> Optional[dict]:
    if not custom_llm_provider:
        return None

    try:
        config_class = None
        if config_class and hasattr(config_class, "calculate_additional_costs"):
            return config_class.calculate_additional_costs(
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
    except Exception as e:
        log.debug(f"Error calculating additional costs: {e}")

    return None


def _transcription_usage_has_token_details(
    usage_block: Optional[Usage],
) -> bool:
    if usage_block is None:
        return False

    prompt_tokens_val = getattr(usage_block, "prompt_tokens", 0) or 0
    completion_tokens_val = getattr(usage_block, "completion_tokens", 0) or 0
    prompt_details = getattr(usage_block, "prompt_tokens_details", None)

    if prompt_details is not None:
        audio_token_count = getattr(prompt_details, "audio_tokens", 0) or 0
        text_token_count = getattr(prompt_details, "text_tokens", 0) or 0
        if audio_token_count > 0 or text_token_count > 0:
            return True

    return (prompt_tokens_val > 0) or (completion_tokens_val > 0)


def cost_per_token(  # noqa: PLR0915
    model: str = "",
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    response_time_ms: Optional[float] = 0.0,
    custom_llm_provider: Optional[str] = None,
    region_name=None,
    ### CHARACTER PRICING ###
    prompt_characters: Optional[int] = None,
    completion_characters: Optional[int] = None,
    ### PROMPT CACHING PRICING ### - used for anthropic
    cache_creation_input_tokens: Optional[int] = 0,
    cache_read_input_tokens: Optional[int] = 0,
    ### CUSTOM PRICING ###
    custom_cost_per_token: Optional[CostPerToken] = None,
    custom_cost_per_second: Optional[float] = None,
    ### NUMBER OF QUERIES ###
    number_of_queries: Optional[int] = None,
    ### USAGE OBJECT ###
    usage_object: Optional[Usage] = None,  # just read the usage object if provided
    ### BILLED UNITS ###
    rerank_billed_units: Optional[RerankBilledUnits] = None,
    ### CALL TYPE ###
    call_type: CallTypesLiteral = "completion",
    audio_transcription_file_duration: float = 0.0,  # for audio transcription calls - the file time in seconds
    ### SERVICE TIER ###
    service_tier: Optional[str] = None,  # for OpenAI service tier pricing
    ### DATA RESIDENCY ###
    data_residency: Optional[
        str
    ] = None,  # for OpenAI regional-processing uplift (e.g. "eu", "us")
    response: Optional[Any] = None,
    ### REQUEST MODEL ###
    request_model: Optional[str] = None,  # original request model for router detection
) -> Tuple[float, float]:  # type: ignore
    if model is None:
        raise Exception("Invalid arg. Model cannot be none.")

    ## RECONSTRUCT USAGE BLOCK ##
    if usage_object is not None:
        usage_block = usage_object
    else:
        usage_block = Usage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            cache_creation_input_tokens=cache_creation_input_tokens,
            cache_read_input_tokens=cache_read_input_tokens,
        )

    _cache_read_tokens: float = 0
    _cache_creation_tokens: float = 0
    _is_anthropic_style = False
    if usage_object is not None:
        _pt_details = getattr(usage_object, "prompt_tokens_details", None)
        if _pt_details is not None:
            _cache_read_tokens = float(getattr(_pt_details, "cached_tokens", 0) or 0)
            # OpenAI-compatible providers report cache-write tokens under
            # either `cache_write_tokens` (kimi-k2) or `cache_creation_tokens`.
            # Mirror db_spend_update_writer to stay symmetric.
            _cache_creation_tokens = float(
                getattr(_pt_details, "cache_write_tokens", 0)
                or getattr(_pt_details, "cache_creation_tokens", 0)
                or 0
            )

        _anthropic_read = getattr(usage_object, "cache_read_input_tokens", None)
        _anthropic_create = getattr(usage_object, "cache_creation_input_tokens", None)
        if _anthropic_read is not None or _anthropic_create is not None:
            _is_anthropic_style = True
            if _anthropic_read is not None:
                _cache_read_tokens = float(_anthropic_read)
            if _anthropic_create is not None:
                _cache_creation_tokens = float(_anthropic_create)

    if not _cache_read_tokens and cache_read_input_tokens:
        _cache_read_tokens = float(cache_read_input_tokens)
        _is_anthropic_style = True
    if not _cache_creation_tokens and cache_creation_input_tokens:
        _cache_creation_tokens = float(cache_creation_input_tokens)
        _is_anthropic_style = True

    # Anthropic reports prompt_tokens as input_tokens (excluding cache tokens).
    # Adjust so the helper's "prompt_tokens includes cache tokens" invariant holds.
    _normalized_prompt_tokens = float(prompt_tokens)
    if _is_anthropic_style:
        _normalized_prompt_tokens += _cache_read_tokens + _cache_creation_tokens

    response_cost = _cost_per_token_custom_pricing_helper(
        prompt_tokens=_normalized_prompt_tokens,
        completion_tokens=completion_tokens,
        response_time_ms=response_time_ms,
        cached_tokens=_cache_read_tokens,
        cache_creation_tokens=_cache_creation_tokens,
        custom_cost_per_second=custom_cost_per_second,
        custom_cost_per_token=custom_cost_per_token,
    )

    if response_cost is not None:
        return response_cost[0], response_cost[1]

    # given
    prompt_tokens_cost_usd_dollar: float = 0
    completion_tokens_cost_usd_dollar: float = 0
    model_cost_ref = model_cost
    caller_supplied_provider = custom_llm_provider is not None

    # `model` is normally a string, but callers that mock the transport can pass
    # non-string objects. Only run the string-based dedup/prefix-join when it is
    # actually a string — e.g. a MagicMock's `.startswith()` is always truthy and
    # its slices return new mocks, which would spin the dedup loop forever.
    model_is_str = isinstance(model, str)

    # Router/proxy deployments may repeat the provider segment (e.g. model_name
    # "openai/openai/gpt-5.5"). Strip duplicated `{provider}/` chains before joining.
    if caller_supplied_provider and model_is_str:
        _dup_prefix = f"{custom_llm_provider}/"
        while model.startswith(_dup_prefix):
            _remainder = model[len(_dup_prefix) :]
            if _remainder.startswith(_dup_prefix):
                model = _remainder
            else:
                break

    model_with_provider = model
    if caller_supplied_provider:
        _prov_prefix = f"{custom_llm_provider}/"
        if model_is_str and model.startswith(_prov_prefix):
            model_with_provider = model
        else:
            model_with_provider = f"{custom_llm_provider}/{model}"
        if region_name is not None:
            model_with_provider_and_region = (
                f"{custom_llm_provider}/{region_name}/{model}"
            )
            if (
                model_with_provider_and_region in model_cost_ref
            ):  # use region based pricing, if it's available
                model_with_provider = model_with_provider_and_region
    else:
        _, custom_llm_provider, _, _ = get_llm_provider(model=model)

    assert custom_llm_provider is not None  # caller-supplied or get_llm_provider

    model_without_prefix = model
    model_parts = model.split("/", 1)
    if len(model_parts) > 1:
        model_without_prefix = model_parts[1]
    else:
        model_without_prefix = model

    if (
        model_with_provider in model_cost_ref
    ):  # Option 2. use model with provider, model = "openai/gpt-4"
        model = model_with_provider
    elif model in model_cost_ref:  # Option 1. use model passed, model="gpt-4"
        model = model
    elif (
        model_without_prefix in model_cost_ref
    ):  # Option 3. if user passed model="bedrock/anthropic.claude-3", use model="anthropic.claude-3"
        model = model_without_prefix

    if custom_llm_provider == "anthropic":
        return anthropic_cost_per_token(model=model, usage=usage_block)
    elif custom_llm_provider == "openai":
        return openai_cost_per_token(
            model=model,
            usage=usage_block,
            service_tier=service_tier,
            data_residency=data_residency,
        )
    elif custom_llm_provider == "gemini":
        return gemini_cost_per_token(
            model=model, usage=usage_block, service_tier=service_tier
        )
    else:
        model_info = _get_model_info_helper(model=model, custom_llm_provider=custom_llm_provider)
        if (model_info.get("input_cost_per_token") or 0.0) > 0 or (
            model_info.get("output_cost_per_token") or 0.0
        ) > 0:
            return generic_cost_per_token(
                model=model,
                usage=usage_block,
                custom_llm_provider=custom_llm_provider,
                service_tier=service_tier,
                data_residency=data_residency,
            )

        if (
            model_info.get("input_cost_per_second", None) is not None
            and response_time_ms is not None
        ):
            log.debug(
                "For model=%s - input_cost_per_second: %s; response time: %s",
                model,
                model_info.get("input_cost_per_second", None),
                response_time_ms,
            )
            ## COST PER SECOND ##
            prompt_tokens_cost_usd_dollar = (
                model_info["input_cost_per_second"] * response_time_ms / 1000  # type: ignore
            )

        if (
            model_info.get("output_cost_per_second", None) is not None
            and response_time_ms is not None
        ):
            log.debug(
                "For model=%s - output_cost_per_second: %s; response time: %s",
                model,
                model_info.get("output_cost_per_second", None),
                response_time_ms,
            )
            ## COST PER SECOND ##
            completion_tokens_cost_usd_dollar = (
                model_info["output_cost_per_second"] * response_time_ms / 1000  # type: ignore
            )

        log.debug(
            "Returned custom cost for model=%s - prompt_tokens_cost_usd_dollar: %s, completion_tokens_cost_usd_dollar: %s",
            model,
            prompt_tokens_cost_usd_dollar,
            completion_tokens_cost_usd_dollar,
        )
        return prompt_tokens_cost_usd_dollar, completion_tokens_cost_usd_dollar


def get_replicate_completion_pricing(completion_response: dict, total_time=0.0):
    # see https://replicate.com/pricing
    # for all litellm currently supported LLMs, almost all requests go to a100_80gb
    a100_80gb_price_per_second_public = DEFAULT_REPLICATE_GPU_PRICE_PER_SECOND  # assume all calls sent to A100 80GB for now
    if total_time == 0.0:  # total time is in ms
        start_time = completion_response.get("created", time.time())
        end_time = getattr(completion_response, "ended", time.time())
        total_time = end_time - start_time

    return a100_80gb_price_per_second_public * total_time / 1000


def has_hidden_params(obj: Any) -> bool:
    return hasattr(obj, "_hidden_params")


def _get_provider_for_cost_calc(
    model: Optional[str],
    custom_llm_provider: Optional[str] = None,
) -> Optional[str]:
    if custom_llm_provider is not None:
        return custom_llm_provider
    if model is None:
        return None
    try:
        _, custom_llm_provider, _, _ = get_llm_provider(model=model)
    except Exception as e:
        log.debug(
            f"calculator.calc::_get_provider_for_cost_calc() - Error inferring custom_llm_provider - {str(e)}"
        )
        return None

    return custom_llm_provider


def _select_model_name_for_cost_calc(
    model: Optional[str],
    completion_response: Optional[Any],
    base_model: Optional[str] = None,
    custom_pricing: Optional[bool] = None,
    custom_llm_provider: Optional[str] = None,
    router_model_id: Optional[str] = None,
) -> Optional[str]:
    return_model: Optional[str] = None
    region_name: Optional[str] = None
    custom_llm_provider = _get_provider_for_cost_calc(
        model=model, custom_llm_provider=custom_llm_provider
    )

    completion_response_model: Optional[str] = None
    if completion_response is not None:
        if isinstance(completion_response, BaseModel):
            completion_response_model = getattr(completion_response, "model", None)
        elif isinstance(completion_response, dict):
            completion_response_model = completion_response.get("model", None)
    hidden_params: Optional[dict] = getattr(completion_response, "_hidden_params", None)

    if custom_pricing is True:
        if router_model_id is not None and router_model_id in model_cost:
            entry = model_cost[router_model_id]
            if (
                entry.get("input_cost_per_token") is not None
                or entry.get("input_cost_per_second") is not None
            ):
                return_model = router_model_id
            else:
                return_model = model
        else:
            return_model = model

    elif base_model is not None:
        return_model = base_model

    elif completion_response_model is None and hidden_params is not None:
        if (
            hidden_params.get("model", None) is not None
            and len(hidden_params["model"]) > 0
        ):
            return_model = hidden_params.get("model", model)
    elif (
        hidden_params is not None and hidden_params.get("region_name", None) is not None
    ):
        region_name = hidden_params.get("region_name", None)

    if return_model is None and completion_response_model is not None:
        return_model = completion_response_model

    if return_model is None and model is not None:
        return_model = model

    if (
        return_model is not None
        and custom_llm_provider is not None
        and not _model_contains_known_llm_provider(return_model)
    ):  # add provider prefix if not already present, to match model_cost
        if region_name is not None:
            return_model = f"{custom_llm_provider}/{region_name}/{return_model}"
        else:
            return_model = f"{custom_llm_provider}/{return_model}"

    return return_model


@lru_cache(maxsize=DEFAULT_MAX_LRU_CACHE_SIZE)
def _model_contains_known_llm_provider(model: str) -> bool:
    """
    Check if the model contains a known llm provider
    """
    _provider_prefix = model.split("/")[0]
    return _provider_prefix in LlmProvidersSet


def _get_response_model(completion_response: Any) -> Optional[str]:
    """
    Extract the model name from a completion response object.

    Used as a fallback for cost calculation when the input model name
    doesn't exist in model_cost (e.g., Azure Model Router).
    """
    if completion_response is None:
        return None

    if isinstance(completion_response, BaseModel):
        return getattr(completion_response, "model", None)
    elif isinstance(completion_response, dict):
        return completion_response.get("model", None)

    return None


_GEMINI_TRAFFIC_TYPE_TO_SERVICE_TIER: dict = {
    # ON_DEMAND_PRIORITY maps to "priority" — selects input_cost_per_token_priority, etc.
    "ON_DEMAND_PRIORITY": "priority",
    # FLEX / BATCH maps to "flex" — selects input_cost_per_token_flex, etc.
    "FLEX": "flex",
    "BATCH": "flex",
    # ON_DEMAND is standard pricing — no service_tier suffix applied
    "ON_DEMAND": None,
}


def _map_traffic_type_to_service_tier(traffic_type: Optional[str]) -> Optional[str]:
    """
    Map a Gemini usageMetadata.trafficType value to a LiteLLM service_tier string.

    This allows the same `_priority` / `_flex` cost-key suffix logic used for
    OpenAI/Azure to work for Gemini and Vertex AI models.

    trafficType values seen in practice
    ------------------------------------
    ON_DEMAND          -> standard pricing  (service_tier = None)
    ON_DEMAND_PRIORITY -> priority pricing  (service_tier = "priority")
    FLEX / BATCH       -> batch/flex pricing (service_tier = "flex")
    """
    if traffic_type is None:
        return None
    service_tier = _GEMINI_TRAFFIC_TYPE_TO_SERVICE_TIER.get(str(traffic_type).upper())
    return service_tier


def _get_usage_object(
    completion_response: Any,
) -> Optional[Usage]:
    usage_obj = cast(
        Union[Usage, ResponseAPIUsage, dict, BaseModel],
        (
            completion_response.get("usage")
            if isinstance(completion_response, dict)
            else getattr(completion_response, "get", lambda x: None)("usage")
        ),
    )

    if usage_obj is None:
        return None
    if isinstance(usage_obj, Usage):
        return usage_obj
    elif isinstance(usage_obj, dict):
        return Usage(**usage_obj)
    elif isinstance(usage_obj, BaseModel):
        return Usage(**usage_obj.model_dump())
    else:
        log.debug(
            f"Unknown usage object type: {type(usage_obj)}, usage_obj: {usage_obj}"
        )
        return None


def _is_known_usage_objects(usage_obj):
    """Returns True if the usage obj is a known Usage type"""
    return (
        isinstance(usage_obj, config.Usage)
        or isinstance(usage_obj, ResponseAPIUsage)
        or TranscriptionUsageObjectTransformation.is_transcription_usage_object(
            usage_obj
        )
    )


def _infer_call_type(
    call_type: Optional[CallTypesLiteral], completion_response: Any
) -> Optional[CallTypesLiteral]:
    if call_type is not None:
        return call_type

    if completion_response is None:
        return None

    if isinstance(completion_response, ModelResponse) or isinstance(
        completion_response, ModelResponseStream
    ):
        return "completion"
    elif isinstance(completion_response, EmbeddingResponse):
        return "embedding"
    elif isinstance(completion_response, TranscriptionResponse):
        return "transcription"
    elif isinstance(completion_response, HttpxBinaryResponseContent):
        return "speech"
    elif isinstance(completion_response, RerankResponse):
        return "rerank"
    elif isinstance(completion_response, ImageResponse):
        return "image_generation"
    elif isinstance(completion_response, TextCompletionResponse):
        return "text_completion"

    return call_type


def _apply_cost_discount(
    base_cost: float,
    custom_llm_provider: Optional[str],
) -> Tuple[float, float, float]:
    """
    Apply provider-specific cost discount from module-level config.

    Args:
        base_cost: The base cost before discount
        custom_llm_provider: The LLM provider name

    Returns:
        Tuple of (final_cost, discount_percent, discount_amount)
    """
    original_cost = base_cost
    discount_percent = 0.0
    discount_amount = 0.0

    if custom_llm_provider and custom_llm_provider in config.cost_discount_config:
        discount_percent = litellm.cost_discount_config[custom_llm_provider]
        discount_amount = original_cost * discount_percent
        final_cost = original_cost - discount_amount
        log.debug(
            f"Applied {discount_percent*100}% discount to {custom_llm_provider}: "
            f"${original_cost:.6f} -> ${final_cost:.6f} (saved ${discount_amount:.6f})"
        )
        return final_cost, discount_percent, discount_amount
    return base_cost, discount_percent, discount_amount


def _apply_cost_margin(
    base_cost: float,
    custom_llm_provider: Optional[str],
) -> Tuple[float, float, float, float]:
    """
    Apply provider-specific or global cost margin from module-level config.

    Args:
        base_cost: The base cost before margin (after discount if applicable)
        custom_llm_provider: The LLM provider name

    Returns:
        Tuple of (final_cost, margin_percent, margin_fixed_amount, margin_total_amount)
    """
    original_cost = base_cost
    margin_percent = 0.0
    margin_fixed_amount = 0.0
    margin_total_amount = 0.0

    # Get margin config - check provider-specific first, then global
    margin_config = None
    if custom_llm_provider and custom_llm_provider in config.cost_margin_config:
        margin_config = config.cost_margin_config[custom_llm_provider]
        log.debug(f"Found provider-specific margin config for {custom_llm_provider}: {margin_config}")
    elif "global" in config.cost_margin_config:
        margin_config = config.cost_margin_config["global"]
        log.debug(f"Using global margin config: {margin_config}")
    else:
        log.debug(
            f"No margin config found. Provider: {custom_llm_provider}, Available configs: {list(config.cost_margin_config.keys())}"
        )

    if margin_config is not None:
        # Handle different margin config formats
        if isinstance(margin_config, (int, float)):
            # Simple percentage: {"openai": 0.10}
            margin_percent = float(margin_config)
            margin_total_amount = original_cost * margin_percent
        elif isinstance(margin_config, dict):
            # Complex config: {"percentage": 0.08, "fixed_amount": 0.0005}
            if "percentage" in margin_config:
                margin_percent = float(margin_config["percentage"])
                margin_total_amount += original_cost * margin_percent
            if "fixed_amount" in margin_config:
                margin_fixed_amount = float(margin_config["fixed_amount"])
                margin_total_amount += margin_fixed_amount

        final_cost = original_cost + margin_total_amount
        log.debug(
            f"Applied margin to {custom_llm_provider or 'global'}: "
            f"${original_cost:.6f} -> ${final_cost:.6f} "
            f"(margin: {margin_percent*100 if margin_percent > 0 else 0}% + ${margin_fixed_amount:.6f} = ${margin_total_amount:.6f})"
        )

        return final_cost, margin_percent, margin_fixed_amount, margin_total_amount

    return base_cost, margin_percent, margin_fixed_amount, margin_total_amount


def _store_cost_breakdown_in_logging_obj(
    litellm_logging_obj: Optional[LitellmLoggingObject],
    prompt_tokens_cost_usd_dollar: float,
    completion_tokens_cost_usd_dollar: float,
    cost_for_built_in_tools_cost_usd_dollar: float,
    total_cost_usd_dollar: float,
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
    """
    Helper function to store cost breakdown in the logging object.

    Args:
        litellm_logging_obj: The logging object to store breakdown in
        prompt_tokens_cost_usd_dollar: Cost of input tokens
        completion_tokens_cost_usd_dollar: Cost of completion tokens (includes reasoning if applicable)
        cost_for_built_in_tools_cost_usd_dollar: Cost of built-in tools
        total_cost_usd_dollar: Total cost of request
        additional_costs: Free-form additional costs dict (e.g., {"azure_model_router_flat_cost": 0.00014})
        original_cost: Cost before discount
        discount_percent: Discount percentage applied (0.05 = 5%)
        discount_amount: Discount amount in USD
        margin_percent: Margin percentage applied (0.10 = 10%)
        margin_fixed_amount: Fixed margin amount in USD
        margin_total_amount: Total margin added in USD
    """
    if litellm_logging_obj is None:
        return

    try:
        # Store the cost breakdown
        litellm_logging_obj.set_cost_breakdown(
            input_cost=prompt_tokens_cost_usd_dollar,
            output_cost=completion_tokens_cost_usd_dollar,
            total_cost=total_cost_usd_dollar,
            cost_for_built_in_tools_cost_usd_dollar=cost_for_built_in_tools_cost_usd_dollar,
            additional_costs=additional_costs,
            original_cost=original_cost,
            discount_percent=discount_percent,
            discount_amount=discount_amount,
            margin_percent=margin_percent,
            margin_fixed_amount=margin_fixed_amount,
            margin_total_amount=margin_total_amount,
            cache_read_cost=cache_read_cost,
            cache_creation_cost=cache_creation_cost,
        )

    except Exception as breakdown_error:
        log.debug(f"Error storing cost breakdown: {str(breakdown_error)}")
        # Don't fail the main cost calculation if breakdown storage fails
        pass


def completion_cost(  # noqa: PLR0915
    completion_response=None,
    model: Optional[str] = None,
    prompt="",
    messages: List = [],
    completion="",
    total_time: Optional[float] = 0.0,  # used for replicate, sagemaker
    call_type: Optional[CallTypesLiteral] = None,
    ### REGION ###
    custom_llm_provider=None,
    region_name=None,  # used for bedrock pricing
    ### IMAGE GEN ###
    size: Optional[str] = None,
    quality: Optional[str] = None,
    n: Optional[int] = None,  # number of images
    ### CUSTOM PRICING ###
    custom_cost_per_token: Optional[CostPerToken] = None,
    custom_cost_per_second: Optional[float] = None,
    optional_params: Optional[dict] = None,
    custom_pricing: Optional[bool] = None,
    base_model: Optional[str] = None,
    standard_built_in_tools_params: Optional[StandardBuiltInToolsParams] = None,
    litellm_model_name: Optional[str] = None,
    router_model_id: Optional[str] = None,
    litellm_logging_obj: Optional[LitellmLoggingObject] = None,
    ### SERVICE TIER ###
    service_tier: Optional[str] = None,  # for OpenAI service tier pricing
    ### DATA RESIDENCY ###
    data_residency: Optional[
        str
    ] = None,  # for OpenAI regional-processing uplift (e.g. "eu", "us")
) -> float:
    try:
        call_type = _infer_call_type(call_type, completion_response) or "completion"

        if (
            (call_type == "aimage_generation" or call_type == "image_generation")
            and model is not None
            and isinstance(model, str)
            and len(model) == 0
            and custom_llm_provider == "azure"
        ):
            model = "dall-e-2"  # for dall-e-2, azure expects an empty model name
        # Handle Inputs to completion_cost
        prompt_tokens = 0
        prompt_characters: Optional[int] = None
        completion_tokens = 0
        completion_characters: Optional[int] = None
        cache_creation_input_tokens: Optional[int] = None
        cache_read_input_tokens: Optional[int] = None
        audio_transcription_file_duration: float = 0.0
        cost_per_token_usage_object: Optional[Usage] = _get_usage_object(
            completion_response=completion_response
        )
        rerank_billed_units: Optional[RerankBilledUnits] = None

        # Extract service_tier from optional_params if not provided directly
        if service_tier is None and optional_params is not None:
            service_tier = optional_params.get("service_tier")

        # Extract service_tier from completion_response if not provided
        if service_tier is None and completion_response is not None:
            if isinstance(completion_response, BaseModel):
                service_tier = getattr(completion_response, "service_tier", None)
            elif isinstance(completion_response, dict):
                service_tier = completion_response.get("service_tier")

        # Extract service_tier from usage object if not provided
        if service_tier is None and cost_per_token_usage_object is not None:
            if isinstance(cost_per_token_usage_object, BaseModel):
                service_tier = getattr(
                    cost_per_token_usage_object, "service_tier", None
                )
            elif isinstance(cost_per_token_usage_object, dict):
                service_tier = cost_per_token_usage_object.get("service_tier")

        selected_model = _select_model_name_for_cost_calc(
            model=model,
            completion_response=completion_response,
            custom_llm_provider=custom_llm_provider,
            custom_pricing=custom_pricing,
            base_model=base_model,
            router_model_id=router_model_id,
        )

        potential_model_names = [
            selected_model,
            _get_response_model(completion_response),
        ]
        if model is not None:
            potential_model_names.append(model)

        for idx, model in enumerate(potential_model_names):
            try:
                log.debug(f"selected model name for cost calculation: {model}")
                if completion_response is not None and (
                    isinstance(completion_response, BaseModel)
                    or isinstance(completion_response, dict)
                ):  # tts returns a custom class
                    if isinstance(completion_response, dict):
                        usage_obj: Optional[Union[dict, Usage]] = (
                            completion_response.get("usage", {})
                        )
                    else:
                        usage_obj = getattr(completion_response, "usage", {})
                    if isinstance(usage_obj, BaseModel) and not _is_known_usage_objects(
                        usage_obj=usage_obj
                    ):
                        _usage_for_dump = cast(BaseModel, usage_obj)
                        setattr(completion_response, "usage", config.Usage(**_usage_for_dump.model_dump()),)
                    if usage_obj is None:
                        _usage = {}
                    elif isinstance(usage_obj, BaseModel):
                        _usage = cast(BaseModel, usage_obj).model_dump()
                    else:
                        _usage = usage_obj

                    # get input/output tokens from completion_response
                    prompt_tokens = _usage.get("prompt_tokens", 0)
                    completion_tokens = _usage.get("completion_tokens", 0)
                    cache_creation_input_tokens = _usage.get(
                        "cache_creation_input_tokens", 0
                    )
                    cache_read_input_tokens = _usage.get("cache_read_input_tokens", 0)
                    if (
                        "prompt_tokens_details" in _usage
                        and _usage["prompt_tokens_details"] != {}
                        and _usage["prompt_tokens_details"]
                    ):
                        prompt_tokens_details = (
                            _usage.get("prompt_tokens_details") or {}
                        )
                        cache_read_input_tokens = prompt_tokens_details.get(
                            "cached_tokens", 0
                        )

                    total_time = getattr(completion_response, "_response_ms", 0)

                    hidden_params = getattr(completion_response, "_hidden_params", None)
                    if hidden_params is not None:
                        custom_llm_provider = hidden_params.get(
                            "custom_llm_provider", custom_llm_provider or None
                        )
                        region_name = hidden_params.get("region_name", region_name)

                        # For Gemini/Vertex AI responses, trafficType is stored in
                        # provider_specific_fields.  Map it to the service_tier used
                        # by the cost key lookup (_priority / _flex suffixes) so that
                        # ON_DEMAND_PRIORITY requests are billed at priority prices.
                        if service_tier is None:
                            provider_specific = (
                                hidden_params.get("provider_specific_fields") or {}
                            )
                            raw_traffic_type = provider_specific.get("traffic_type")
                            if raw_traffic_type:
                                service_tier = _map_traffic_type_to_service_tier(
                                    raw_traffic_type
                                )
                else:
                    if model is None:
                        raise ValueError(
                            f"Model is None and does not exist in passed completion_response. Passed completion_response={completion_response}, model={model}"
                        )
                    if len(messages) > 0:
                        prompt_tokens = token_counter(model=model, messages=messages)
                    elif len(prompt) > 0:
                        prompt_tokens = token_counter(model=model, text=prompt)
                    completion_tokens = token_counter(model=model, text=completion)

                if model is None:
                    raise ValueError(
                        f"Model is None and does not exist in passed completion_response. Passed completion_response={completion_response}, model={model}"
                    )
                if custom_llm_provider is None:
                    try:
                        model, custom_llm_provider, _, _ = get_llm_provider(
                            model=model
                        )  # strip the llm provider from the model name -> for image gen cost calculation
                    except Exception as e:
                        log.debug("calculator.calc::completion_cost() - Error inferring custom_llm_provider - {}".format(str(e)))
                if CostCalculatorUtils._call_type_has_image_response(
                    call_type
                ) and isinstance(completion_response, ImageResponse):
                    ### IMAGE GENERATION COST CALCULATION ###
                    return CostCalculatorUtils.route_image_generation_cost_calculator(
                        model=model,
                        custom_llm_provider=custom_llm_provider,
                        completion_response=completion_response,
                        quality=quality,
                        n=n,
                        size=size,
                        optional_params=optional_params,
                        call_type=call_type,
                    )
                elif call_type in _SPEECH_CALL_TYPES:
                    prompt_characters = config.utils._count_characters(text=prompt)
                elif call_type in _TRANSCRIPTION_CALL_TYPES:
                    # Check _hidden_params first (duration stored there to
                    # avoid polluting the response body), then fall back to
                    # the response attribute (for verbose_json responses that
                    # naturally include duration from the provider).
                    _hidden = getattr(completion_response, "_hidden_params", {}) or {}
                    audio_transcription_file_duration = _hidden.get(
                        "audio_transcription_duration",
                        getattr(completion_response, "duration", 0.0),
                    )
                elif call_type in _RERANK_CALL_TYPES:
                    if completion_response is not None and isinstance(
                        completion_response, RerankResponse
                    ):
                        meta_obj = completion_response.meta
                        if meta_obj is not None:
                            billed_units = meta_obj.get("billed_units", {}) or {}
                        else:
                            billed_units = {}

                        rerank_billed_units = RerankBilledUnits(
                            search_units=billed_units.get("search_units"),
                            total_tokens=billed_units.get("total_tokens"),
                        )

                        search_units = (
                            billed_units.get("search_units") or 1
                        )  # cohere charges per request by default.
                        completion_tokens = search_units
                elif call_type == _AREALTIME_CALL_TYPE and isinstance(
                    completion_response, LiteLLMRealtimeStreamLoggingObject
                ):
                    if (
                        cost_per_token_usage_object is None
                        or custom_llm_provider is None
                    ):
                        raise ValueError(
                            "usage object and custom_llm_provider must be provided for realtime stream cost calculation. Got cost_per_token_usage_object={}, custom_llm_provider={}".format(
                                cost_per_token_usage_object,
                                custom_llm_provider,
                            )
                        )
                    return handle_realtime_stream_cost_calculation(
                        results=completion_response.results,
                        combined_usage_object=cost_per_token_usage_object,
                        custom_llm_provider=custom_llm_provider,
                        litellm_model_name=model,
                        data_residency=data_residency,
                    )

                if (
                    "togethercomputer" in model
                    or "together_ai" in model
                    or custom_llm_provider == "together_ai"
                ):
                    # together ai prices based on size of llm
                    # get_model_params_and_category takes a model name and returns the category of LLM size it is in model_prices_and_context_window.json

                    model = get_model_params_and_category(
                        model, call_type=CallTypes(call_type)
                    )

                # replicate llms are calculate based on time for request running
                # see https://replicate.com/pricing
                elif (
                    model in litellm.replicate_models or "replicate" in model
                ) and model not in model_cost:
                    # for unmapped replicate model, default to replicate's time tracking logic
                    return get_replicate_completion_pricing(completion_response, total_time)  # type: ignore

                if model is None:
                    raise ValueError(
                        f"Model is None and does not exist in passed completion_response. Passed completion_response={completion_response}, model={model}"
                    )

                if (
                    custom_llm_provider is not None
                    and custom_llm_provider == "vertex_ai"
                ):
                    # Calculate the prompt characters + response characters
                    if len(messages) > 0:
                        prompt_string = config.utils.get_formatted_prompt(data={"messages": messages}, call_type="completion")
                        prompt_characters = config.utils._count_characters(text=prompt_string)
                    if completion_response is not None and isinstance(completion_response, ModelResponse):
                        completion_string = config.utils.get_response_string(response_obj=completion_response)
                        completion_characters = config.utils._count_characters(text=completion_string)

                # Get the original request model for router detection
                request_model_for_cost = None
                if litellm_logging_obj is not None:
                    request_model_for_cost = litellm_logging_obj.model

                (
                    prompt_tokens_cost_usd_dollar,
                    completion_tokens_cost_usd_dollar,
                ) = cost_per_token(
                    model=model,
                    prompt_tokens=prompt_tokens or 0,
                    completion_tokens=completion_tokens or 0,
                    custom_llm_provider=custom_llm_provider,
                    response_time_ms=total_time,
                    region_name=region_name,
                    custom_cost_per_second=custom_cost_per_second,
                    custom_cost_per_token=custom_cost_per_token,
                    prompt_characters=prompt_characters,
                    completion_characters=completion_characters,
                    cache_creation_input_tokens=cache_creation_input_tokens,
                    cache_read_input_tokens=cache_read_input_tokens,
                    usage_object=cost_per_token_usage_object,
                    call_type=call_type,
                    audio_transcription_file_duration=audio_transcription_file_duration,
                    rerank_billed_units=rerank_billed_units,
                    service_tier=service_tier,
                    data_residency=data_residency,
                    response=completion_response,
                    request_model=request_model_for_cost,
                )

                # Get additional costs from provider (e.g., routing fees, infrastructure costs)
                if custom_llm_provider == "azure_ai":
                    model_for_additional_costs = request_model_for_cost
                    if completion_response is not None:
                        hidden_params = (
                            getattr(completion_response, "_hidden_params", None) or {}
                        )
                        hidden_model = hidden_params.get("model") or hidden_params.get(
                            "litellm_model_name"
                        )
                        if hidden_model and (
                            "model_router" in (hidden_model or "").lower()
                            or "model-router" in (hidden_model or "").lower()
                        ):
                            model_for_additional_costs = hidden_model
                        elif model_for_additional_costs is None:
                            model_for_additional_costs = hidden_model
                    if model_for_additional_costs is None:
                        model_for_additional_costs = model
                    additional_costs = _get_additional_costs(
                        model=model_for_additional_costs,
                        custom_llm_provider=custom_llm_provider,
                        prompt_tokens=prompt_tokens or 0,
                        completion_tokens=completion_tokens or 0,
                    )
                else:
                    additional_costs = None

                _final_cost = (
                    prompt_tokens_cost_usd_dollar + completion_tokens_cost_usd_dollar
                )
                cost_for_built_in_tools = (
                    StandardBuiltInToolCostTracking.get_cost_for_built_in_tools(
                        model=model,
                        response_object=completion_response,
                        usage=cost_per_token_usage_object,
                        standard_built_in_tools_params=standard_built_in_tools_params,
                        custom_llm_provider=custom_llm_provider,
                    )
                )
                _final_cost += cost_for_built_in_tools
                if additional_costs:
                    _final_cost += sum(additional_costs.values())

                original_cost = _final_cost
                if config.cost_discount_config:
                    (
                        _final_cost,
                        discount_percent,
                        discount_amount,
                    ) = _apply_cost_discount(
                        base_cost=_final_cost,
                        custom_llm_provider=custom_llm_provider,
                    )
                else:
                    discount_percent = 0.0
                    discount_amount = 0.0

                # Apply margin from module-level config if configured
                if config.cost_margin_config:
                    (
                        _final_cost,
                        margin_percent,
                        margin_fixed_amount,
                        margin_total_amount,
                    ) = _apply_cost_margin(
                        base_cost=_final_cost,
                        custom_llm_provider=custom_llm_provider,
                    )
                else:
                    margin_percent = 0.0
                    margin_fixed_amount = 0.0
                    margin_total_amount = 0.0

                # Store cost breakdown in logging object if available
                if litellm_logging_obj is not None:
                    _cache_read_cost: Optional[float] = None
                    _cache_creation_cost: Optional[float] = None
                    if cost_per_token_usage_object is not None:
                        _cr = getattr(
                            cost_per_token_usage_object, "cache_read_input_tokens", None
                        ) or (cost_per_token_usage_object.model_extra or {}).get(
                            "cache_read_input_tokens"
                        )
                        _cc = getattr(
                            cost_per_token_usage_object,
                            "cache_creation_input_tokens",
                            None,
                        ) or (cost_per_token_usage_object.model_extra or {}).get(
                            "cache_creation_input_tokens"
                        )
                        if (_cr or _cc) and model:
                            try:
                                _mi = config.get_model_info(model=model, custom_llm_provider=custom_llm_provider)
                                _cr_rate = _mi.get("cache_read_input_token_cost")
                                if _cr and _cr_rate is not None:
                                    _cache_read_cost = float(_cr) * float(_cr_rate)
                                _cc_rate = _mi.get("cache_creation_input_token_cost")
                                if _cc and _cc_rate is not None:
                                    _cache_creation_cost = float(_cc) * float(_cc_rate)
                            except Exception:
                                pass
                    _store_cost_breakdown_in_logging_obj(
                        litellm_logging_obj=litellm_logging_obj,
                        prompt_tokens_cost_usd_dollar=prompt_tokens_cost_usd_dollar,
                        completion_tokens_cost_usd_dollar=completion_tokens_cost_usd_dollar,
                        cost_for_built_in_tools_cost_usd_dollar=cost_for_built_in_tools,
                        total_cost_usd_dollar=_final_cost,
                        original_cost=original_cost,
                        additional_costs=additional_costs,
                        discount_percent=discount_percent,
                        discount_amount=discount_amount,
                        margin_percent=margin_percent,
                        margin_fixed_amount=margin_fixed_amount,
                        margin_total_amount=margin_total_amount,
                        cache_read_cost=_cache_read_cost,
                        cache_creation_cost=_cache_creation_cost,
                    )

                return _final_cost
            except Exception as e:
                log.debug(
                    "calculator.calc::completion_cost() - Error calculating cost for model={} - {}".format(
                        model, str(e)
                    )
                )
                if idx == len(potential_model_names) - 1:
                    raise e
        raise Exception(
            "Unable to calculat cost for received potential model names - {}".format(
                potential_model_names
            )
        )
    except Exception as e:
        raise e


def get_response_cost_from_hidden_params(
    hidden_params: Union[dict, BaseModel],
) -> Optional[float]:
    if isinstance(hidden_params, BaseModel):
        _hidden_params_dict = cast(BaseModel, hidden_params).model_dump()
    else:
        _hidden_params_dict = hidden_params

    additional_headers = _hidden_params_dict.get("additional_headers", {})
    if (
        additional_headers
        and "llm_provider-x-litellm-response-cost" in additional_headers
    ):
        response_cost = additional_headers["llm_provider-x-litellm-response-cost"]
        if response_cost is None:
            return None
        return float(additional_headers["llm_provider-x-litellm-response-cost"])
    return None


def response_cost_calculator(
    response_object: Union[
        ModelResponse,
        EmbeddingResponse,
        ImageResponse,
        TranscriptionResponse,
        TextCompletionResponse,
        HttpxBinaryResponseContent,
        RerankResponse,
        ResponsesAPIResponse,
        LiteLLMRealtimeStreamLoggingObject,
        OpenAIModerationResponse,
        Response
    ],
    model: str,
    custom_llm_provider: Optional[str],
    call_type: Literal[
        "embedding",
        "aembedding",
        "completion",
        "acompletion",
        "atext_completion",
        "text_completion",
        "image_generation",
        "aimage_generation",
        "moderation",
        "amoderation",
        "atranscription",
        "transcription",
        "aspeech",
        "speech",
        "rerank",
        "arerank",
        "search",
        "asearch",
    ],
    optional_params: dict,
    cache_hit: Optional[bool] = None,
    base_model: Optional[str] = None,
    custom_pricing: Optional[bool] = None,
    prompt: str = "",
    standard_built_in_tools_params: Optional[StandardBuiltInToolsParams] = None,
    litellm_model_name: Optional[str] = None,
    router_model_id: Optional[str] = None,
    litellm_logging_obj: Optional[LitellmLoggingObject] = None,
    ### SERVICE TIER ###
    service_tier: Optional[str] = None,  # for OpenAI service tier pricing
    ### DATA RESIDENCY ###
    data_residency: Optional[
        str
    ] = None,  # for OpenAI regional-processing uplift (e.g. "eu", "us")
) -> float:
    """
    Returns
    - float or None: cost of response
    """
    try:
        response_cost: float = 0.0
        if cache_hit is not None and cache_hit is True:
            response_cost = 0.0
        else:
            if isinstance(response_object, BaseModel):
                if hasattr(response_object, "_hidden_params"):
                    response_object._hidden_params["optional_params"] = optional_params
                    provider_response_cost = get_response_cost_from_hidden_params(
                        response_object._hidden_params
                    )
                    if provider_response_cost is not None:
                        return provider_response_cost

            response_cost = completion_cost(
                completion_response=response_object,
                model=model,
                call_type=call_type,
                custom_llm_provider=custom_llm_provider,
                optional_params=optional_params,
                custom_pricing=custom_pricing,
                base_model=base_model,
                prompt=prompt,
                standard_built_in_tools_params=standard_built_in_tools_params,
                litellm_model_name=litellm_model_name,
                router_model_id=router_model_id,
                litellm_logging_obj=litellm_logging_obj,
                service_tier=service_tier,
                data_residency=data_residency,
            )
        return response_cost
    except Exception as e:
        raise e

class BaseTokenUsageProcessor:
    @staticmethod
    def combine_usage_objects(usage_objects: List[Usage]) -> Usage:
        """
        Combine multiple Usage objects into a single Usage object, checking model keys for nested values.
        """
        from channel.model.types.utils import (
            CompletionTokensDetailsWrapper,
            PromptTokensDetailsWrapper,
            Usage,
        )

        combined = Usage()

        # Sum basic token counts
        for usage in usage_objects:
            # Handle direct attributes by checking what exists in the model
            for attr in dir(usage):
                if not attr.startswith("_") and not callable(getattr(usage, attr)):
                    current_val = getattr(combined, attr, 0)
                    new_val = getattr(usage, attr, 0)
                    if (
                        new_val is not None
                        and isinstance(new_val, (int, float))
                        and isinstance(current_val, (int, float))
                    ):
                        setattr(combined, attr, current_val + new_val)
            # Handle nested prompt_tokens_details
            if hasattr(usage, "prompt_tokens_details") and usage.prompt_tokens_details:
                if (
                    not hasattr(combined, "prompt_tokens_details")
                    or not combined.prompt_tokens_details
                ):
                    combined.prompt_tokens_details = PromptTokensDetailsWrapper()

                # Check what keys exist in the model's prompt_tokens_details
                # Access model_fields on the class, not the instance, to avoid Pydantic 2.11+ deprecation warnings
                for attr in type(usage.prompt_tokens_details).model_fields:
                    if (
                        hasattr(usage.prompt_tokens_details, attr)
                        and not attr.startswith("_")
                        and not callable(getattr(usage.prompt_tokens_details, attr))
                    ):
                        current_val = (
                            getattr(combined.prompt_tokens_details, attr, 0) or 0
                        )
                        new_val = getattr(usage.prompt_tokens_details, attr, 0) or 0
                        if new_val is not None and isinstance(new_val, (int, float)):
                            setattr(
                                combined.prompt_tokens_details,
                                attr,
                                current_val + new_val,
                            )

            # Handle nested completion_tokens_details
            if (
                hasattr(usage, "completion_tokens_details")
                and usage.completion_tokens_details
            ):
                if (
                    not hasattr(combined, "completion_tokens_details")
                    or not combined.completion_tokens_details
                ):
                    combined.completion_tokens_details = (
                        CompletionTokensDetailsWrapper()
                    )

                # Check what keys exist in the model's completion_tokens_details
                # Access model_fields on the class, not the instance, to avoid Pydantic 2.11+ deprecation warnings
                for attr in type(usage.completion_tokens_details).model_fields:
                    if not attr.startswith("_") and not callable(
                        getattr(usage.completion_tokens_details, attr)
                    ):
                        current_val = (
                            getattr(combined.completion_tokens_details, attr, 0) or 0
                        )
                        new_val = getattr(usage.completion_tokens_details, attr, 0) or 0
                        if isinstance(new_val, (int, float)):
                            setattr(
                                combined.completion_tokens_details,
                                attr,
                                current_val + new_val,
                            )

        return combined


class RealtimeAPITokenUsageProcessor(BaseTokenUsageProcessor):
    @staticmethod
    def collect_usage_from_realtime_stream_results(
        results: OpenAIRealtimeStreamList,
    ) -> List[Usage]:
        response_done_events: List[OpenAIRealtimeStreamResponseBaseObject] = cast(
            List[OpenAIRealtimeStreamResponseBaseObject],
            [result for result in results if result["type"] == "response.done"],
        )
        usage_objects: List[Usage] = []
        return usage_objects

    @staticmethod
    def collect_and_combine_usage_from_realtime_stream_results(
        results: OpenAIRealtimeStreamList,
    ) -> Usage:
        """
        Collect and combine usage from realtime stream results
        """
        collected_usage_objects = (
            RealtimeAPITokenUsageProcessor.collect_usage_from_realtime_stream_results(
                results
            )
        )
        combined_usage_object = RealtimeAPITokenUsageProcessor.combine_usage_objects(
            collected_usage_objects
        )
        return combined_usage_object

    @staticmethod
    def create_logging_realtime_object(
        usage: Usage, results: OpenAIRealtimeStreamList
    ) -> LiteLLMRealtimeStreamLoggingObject:
        return LiteLLMRealtimeStreamLoggingObject(
            usage=usage,
            results=results,
        )


def handle_realtime_stream_cost_calculation(
    results: OpenAIRealtimeStreamList,
    combined_usage_object: Usage,
    custom_llm_provider: str,
    litellm_model_name: str,
    data_residency: Optional[str] = None,
) -> float:
    """
    Handles the cost calculation for realtime stream responses.

    Pick the 'response.done' events. Calculate total cost across all 'response.done' events.

    Args:
        results: A list of OpenAIRealtimeStreamBaseObject objects
    """
    received_model = None
    potential_model_names = []
    for result in results:
        if result["type"] == "session.created":
            received_model = cast(OpenAIRealtimeStreamSessionEvents, result)[
                "session"
            ].get("model", None)
            potential_model_names.append(received_model)

    potential_model_names.append(litellm_model_name)
    input_cost_per_token = 0.0
    output_cost_per_token = 0.0

    for model_name in potential_model_names:
        try:
            if model_name is None:
                continue
            _input_cost_per_token, _output_cost_per_token = generic_cost_per_token(
                model=model_name,
                usage=combined_usage_object,
                custom_llm_provider=custom_llm_provider,
                data_residency=data_residency,
            )
        except Exception:
            continue
        input_cost_per_token += _input_cost_per_token
        output_cost_per_token += _output_cost_per_token
        break  # exit if we find a valid model
    total_cost = input_cost_per_token + output_cost_per_token

    return total_cost
