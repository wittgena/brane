# xphi.scope.plane.telemetry
## @lineage: bound.xor.scope.plane.telemetry
## @lineage: bound.scope.plane.telemetry
## @lineage: bound.plane.telemetry
## @lineage: channel.cost.telemetry
## @lineage: channel.gov.cost.telemetry
import json
import os
import time
import traceback
import warnings
from collections.abc import Callable
from typing import Any, ClassVar
from arch.proto.phase.gate import uuid4
from anchor.model.info.cost.calculator.calc import completion_cost as litellm_completion_cost
from anchor.switch.params import ResponseAPIUsage, ResponsesAPIResponse
from anchor.switch.params import ModelResponse
from bound.adapter.legacy.llm.types.utils import CostPerToken, Usage
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr
from xphi.scope.plane.metrics import Metrics
from watcher.plane.emitter import get_emitter, _flow_context

emitter = get_emitter(__name__, phase="llm_generation", boundary="llm_scope")

class Telemetry(BaseModel):
    """
    Handles latency, token/cost accounting, and optional logging.
    All runtime state (like start times) lives in private attrs.
    """
    model_name: str = Field(default="unknown", description="Name of the LLM model")
    log_enabled: bool = Field(default=False, description="Whether to log completions")
    log_dir: str | None = Field(default=None, description="Directory to write logs if enabled")
    input_cost_per_token: float | None = Field(default=None, ge=0, description="Custom Input cost per token (USD)")
    output_cost_per_token: float | None = Field(default=None, ge=0, description="Custom Output cost per token (USD)")
    metrics: Metrics = Field(..., description="Metrics collector instance")

    ## Runtime fields (not serialized)
    _req_start: float = PrivateAttr(default=0.0)
    _req_ctx: dict[str, Any] = PrivateAttr(default_factory=dict)
    _last_latency: float = PrivateAttr(default=0.0)
    _log_completions_callback: Callable[[str, str], None] | None = PrivateAttr(default=None)
    _stats_update_callback: Callable[[], None] | None = PrivateAttr(default=None)

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    ## Lifecycle
    def set_log_completions_callback(self, callback: Callable[[str, str], None] | None) -> None:
        """Set a callback function for logging instead of writing to file."""
        self._log_completions_callback = callback

    def set_stats_update_callback(self, callback: Callable[[], None] | None) -> None:
        """Set a callback function to be notified when stats are updated."""
        self._stats_update_callback = callback

    def on_request(self, telemetry_ctx: dict | None) -> None:
        self._req_start = time.time()
        self._req_ctx = telemetry_ctx or {}

    def on_response(
        self,
        resp: ModelResponse | ResponsesAPIResponse,
        raw_resp: ModelResponse | None = None,
    ) -> Metrics:
        """
        Side-effects:
          - records latency, tokens, cost into Metrics
          - optionally writes a JSON log file
        """
        ## 내부 서브-콜(Internal Sub-call)로 인한 이중 과금/중복 측정 방지
        ctx = _flow_context.get()
        if ctx.get("is_internal_call"):
            emitter.debug("Skipping telemetry for internal sub-call (is_internal_call=True).")
            return self.metrics.deep_copy()

        ## latency
        self._last_latency = time.time() - (self._req_start or time.time())
        response_id = resp.id
        self.metrics.add_response_latency(self._last_latency, response_id)

        cost = self._compute_cost(resp)
        ## Intentionally skip logging zero-cost (0.0) responses; only record positive cost
        if cost:
            self.metrics.add_cost(cost)

        ## tokens - use typed usage field when available
        usage = getattr(resp, "usage", None)
        if usage and self._has_meaningful_usage(usage):
            self._record_usage(
                usage, response_id, self._req_ctx.get("context_window", 0)
            )

        ## notify about stats update
        if self._stats_update_callback is not None:
            try:
                self._stats_update_callback()
            except Exception:
                emitter.exception("Stats update callback failed", exc_info=True)
        
        raw_usage = usage.model_dump() if usage else {}

        ## 내부 시스템용 정규화된 Metrics 추출
        prompt_tokens = int(getattr(usage, "prompt_tokens", None) or getattr(usage, "input_tokens", 0) or 0)
        completion_tokens = int(getattr(usage, "completion_tokens", None) or getattr(usage, "output_tokens", 0) or 0)
        
        ## 캐시 및 추론 토큰 등 추출 로직
        p_details = getattr(usage, "prompt_tokens_details", None) or getattr(usage, "input_tokens_details", None)
        cache_read_tokens = int(getattr(p_details, "cached_tokens", 0)) if p_details else 0

        payload = {
            "response_id": resp.id,
            "cost": cost,
            "latency_ms": self._last_latency * 1000,
            "model_name": self.model_name,
            "usage": raw_usage,
            "usage_metrics": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "cache_read_tokens": cache_read_tokens
            }
        }
        emitter.signal("LLM_COMPLETION_TRACKED", payload=payload)
        return self.metrics.deep_copy()

    def on_error(self, _err: BaseException) -> None:
        ## 내부 호출 실패 시 불필요한 에러 덤프 건너뛰기
        ctx = _flow_context.get()
        if ctx.get("is_internal_call"):
            emitter.debug("Internal sub-call failed. Skipping telemetry error log.")
            return

        ## Best-effort logging for failed requests (so we can debug malformed
        ## request payloads, e.g. orphaned Responses reasoning items).
        self._last_latency = time.time() - (self._req_start or time.time())

        if not self.log_enabled:
            return
        if not self.log_dir and not self._log_completions_callback:
            return

        try:
            filename = (
                f"{self.model_name.replace('/', '__')}-"
                f"{time.time():.3f}-"
                f"{uuid4().hex[:4]}-error.json"
            )

            data = self._req_ctx.copy()
            data["error"] = {
                "type": type(_err).__name__,
                "message": str(_err),
                "repr": repr(_err),
                "traceback": "".join(
                    traceback.format_exception(type(_err), _err, _err.__traceback__)
                ),
            }
            data["timestamp"] = time.time()
            data["latency_sec"] = self._last_latency
            data["cost"] = 0.0

            log_data = json.dumps(data, default=_safe_json, ensure_ascii=False)
            if self._log_completions_callback:
                self._log_completions_callback(filename, log_data)
            elif self.log_dir:
                os.makedirs(self.log_dir, exist_ok=True)
                fname = os.path.join(self.log_dir, filename)
                with open(fname, "w", encoding="utf-8") as f:
                    f.write(log_data)
        except Exception as e:
            warnings.warn(f"Telemetry error logging failed: {e}")
        return

    def _has_meaningful_usage(self, usage: Usage | ResponseAPIUsage | None) -> bool:
        if usage is None:
            return False
        try:
            prompt_tokens = getattr(usage, "prompt_tokens", None)
            if prompt_tokens is None:
                prompt_tokens = getattr(usage, "input_tokens", 0)
            completion_tokens = getattr(usage, "completion_tokens", None)
            if completion_tokens is None:
                completion_tokens = getattr(usage, "output_tokens", 0)

            pt = int(prompt_tokens or 0)
            ct = int(completion_tokens or 0)
            return pt > 0 or ct > 0
        except Exception:
            return False

    def _record_usage(
        self, usage: Usage | ResponseAPIUsage, response_id: str, context_window: int
    ) -> None:
        prompt_tokens = int(
            getattr(usage, "prompt_tokens", None)
            or getattr(usage, "input_tokens", 0)
            or 0
        )
        completion_tokens = int(
            getattr(usage, "completion_tokens", None)
            or getattr(usage, "output_tokens", 0)
            or 0
        )

        cache_read = 0
        p_details = getattr(usage, "prompt_tokens_details", None) or getattr(
            usage, "input_tokens_details", None
        )
        if p_details is not None:
            cache_read = int(getattr(p_details, "cached_tokens", 0) or 0)

        ## populate usage.cached_tokens field
        if not cache_read and hasattr(usage, "cached_tokens"):
            cache_read = int(getattr(usage, "cached_tokens", 0) or 0)

        reasoning_tokens = 0
        c_details = getattr(usage, "completion_tokens_details", None) or getattr(
            usage, "output_tokens_details", None
        )
        if c_details is not None:
            reasoning_tokens = int(getattr(c_details, "reasoning_tokens", 0) or 0)

        ## Chat-specific - may set a hidden cache write field
        cache_write = int(getattr(usage, "_cache_creation_input_tokens", 0) or 0)
        self.metrics.add_token_usage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cache_read_tokens=cache_read,
            cache_write_tokens=cache_write,
            reasoning_tokens=reasoning_tokens,
            context_window=context_window,
            response_id=response_id,
        )

    def _compute_cost(self, resp: ModelResponse | ResponsesAPIResponse) -> float | None:
        """Try provider header → litellm direct. Return None on failure."""
        extra_kwargs = {}
        if (
            self.input_cost_per_token is not None
            and self.output_cost_per_token is not None
        ):
            cost_per_token = CostPerToken(
                input_cost_per_token=self.input_cost_per_token,
                output_cost_per_token=self.output_cost_per_token,
            )
            emitter.debug(f"Using custom cost per token: {cost_per_token}")
            extra_kwargs["custom_cost_per_token"] = cost_per_token

        try:
            hidden = getattr(resp, "_hidden_params", {}) or {}
            cost = hidden.get("additional_headers", {}).get(
                "llm_provider-x-litellm-response-cost"
            )
            if cost is not None:
                return float(cost)
        except Exception as e:
            emitter.debug(f"Failed to get cost from LiteLLM headers: {e}")

        ## move on to cost calculator
        if "/" in self.model_name:
            provider, bare = self.model_name.split("/", 1)
            extra_kwargs["model"] = bare
            extra_kwargs["custom_llm_provider"] = provider
        else:
            extra_kwargs["model"] = self.model_name
        try:
            return float(litellm_completion_cost(completion_response=resp, **extra_kwargs))
        except Exception as e:
            warnings.warn(f"Cost calculation failed: {e}")
            return None

    ## @plan.delete
    def log_llm_call(
        self,
        resp: ModelResponse | ResponsesAPIResponse,
        cost: float | None,
        raw_resp: ModelResponse | ResponsesAPIResponse | None = None,
    ) -> None:
        # Skip if neither file logging nor callback is configured
        if not self.log_dir and not self._log_completions_callback:
            return
        try:
            filename = (
                f"{self.model_name.replace('/', '__')}-"
                f"{time.time():.3f}-"
                f"{uuid4().hex[:4]}.json"
            )

            data = self._req_ctx.copy()
            data["response"] = resp
            data["cost"] = float(cost or 0.0)
            data["timestamp"] = time.time()
            data["latency_sec"] = self._last_latency

            try:
                usage = getattr(resp, "usage", None)
                if usage:
                    prompt_tokens = int(
                        getattr(usage, "prompt_tokens", None)
                        or getattr(usage, "input_tokens", 0)
                        or 0
                    )
                    completion_tokens = int(
                        getattr(usage, "completion_tokens", None)
                        or getattr(usage, "output_tokens", 0)
                        or 0
                    )
                    details = getattr(
                        usage, "completion_tokens_details", None
                    ) or getattr(usage, "output_tokens_details", None)
                    reasoning_tokens = (
                        int(getattr(details, "reasoning_tokens", 0) or 0)
                        if details
                        else 0
                    )
                    p_details = getattr(
                        usage, "prompt_tokens_details", None
                    ) or getattr(usage, "input_tokens_details", None)
                    cache_read_tokens = (
                        int(getattr(p_details, "cached_tokens", 0) or 0)
                        if p_details
                        else 0
                    )

                    data["usage_summary"] = {
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "reasoning_tokens": reasoning_tokens,
                        "cache_read_tokens": cache_read_tokens,
                    }
            except Exception:
                pass

            if raw_resp:
                data["raw_response"] = raw_resp
            
            if (
                "tools" in data
                and isinstance(data.get("kwargs"), dict)
                and "tools" in data["kwargs"]
            ):
                data["kwargs"].pop("tools")

            log_data = json.dumps(data, default=_safe_json, ensure_ascii=False)

            if self._log_completions_callback:
                self._log_completions_callback(filename, log_data)
            elif self.log_dir:
                os.makedirs(self.log_dir, exist_ok=True)
                if not os.access(self.log_dir, os.W_OK):
                    raise PermissionError(f"log_dir is not writable: {self.log_dir}")
                fname = os.path.join(self.log_dir, filename)
                with open(fname, "w", encoding="utf-8") as f:
                    f.write(log_data)
        except Exception as e:
            warnings.warn(f"Telemetry logging failed: {e}")


def _safe_json(obj: Any) -> Any:
    if isinstance(obj, ModelResponse) or isinstance(obj, ResponsesAPIResponse):
        return obj.model_dump(mode="json", exclude_none=True)

    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json", exclude_none=True)

    try:
        return obj.__dict__
    except Exception:
        return str(obj)