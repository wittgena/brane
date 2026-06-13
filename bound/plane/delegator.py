# bound.plane.delegator
## @lineage: bound.plane
## @lineage: channel.bound.plane
from typing import Any, Dict, List, Optional, Tuple, Union
from channel.model.types.utils import LiteLLMLoggingBaseClass
from bound.plane.telemetry import Telemetry
from bound.plane.metrics import Metrics
from watcher.plane.emitter import get_emitter

## 외부 로거 및 상태 관리용 전역 변수 (ImportError 방어용 Dummy)
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

class Logging(LiteLLMLoggingBaseClass):
    """기존 호출 구조를 유지하면서 내부적으로는 Telemetry 시스템으로 이벤트를 위임"""
    stream: bool = False
    litellm_trace_id: str = "dummy-trace-id"
    model_call_details: dict = {}
    standard_built_in_tools_params: Any = None
    cost_breakdown: dict = {}
    callback_duration_ms: float = 0.0

    def __init__(self, *args, **kwargs):
        try:
            super().__init__(*args, **kwargs)
        except Exception:
            pass
        self.model_call_details = kwargs.get("kwargs", {})
        
        ## 주의: 향후 Metrics 객체는 상위 Context에서 주입받는 형태로 개선 권장
        self._telemetry = Telemetry(
            model_name=kwargs.get("model", "unknown"), 
            metrics=Metrics()
        )
        self._telemetry.on_request(telemetry_ctx=kwargs)

    ## 생명주기 훅 (Telemetry 위임)
    def success_handler(self, result=None, *args, **kwargs):
        if result:
            self._telemetry.on_response(result)
        return super().success_handler(result, *args, **kwargs) if hasattr(super(), 'success_handler') else None

    async def async_success_handler(self, result=None, *args, **kwargs):
        if result:
            self._telemetry.on_response(result)
        return super().async_success_handler(result, *args, **kwargs) if hasattr(super(), 'async_success_handler') else None

    def failure_handler(self, exception, traceback_exception=None, *args, **kwargs):
        self._telemetry.on_error(exception)
        return exception, traceback_exception

    async def async_failure_handler(self, exception, traceback_exception=None, *args, **kwargs):
        self._telemetry.on_error(exception)
        return exception, traceback_exception

    ## --- Dummy 방어선 (에러 방지용)
    def pre_call(self, *args, **kwargs): pass
    def _pre_call(self, *args, **kwargs): pass
    def post_call(self, *args, **kwargs): pass
    
    def update_environment_variables(self, *args, **kwargs): pass
    def update_from_kwargs(self, *args, **kwargs): pass
    def update_messages(self, messages: List[Any]): pass
    def set_cost_breakdown(self, *args, **kwargs): pass
    def _response_cost_calculator(self, *args, **kwargs) -> float: return 0.0

    ## 언패킹 반환 방어 (내부 로직 방어)
    def get_chat_completion_prompt(self, model: str, messages: List[Any], non_default_params: Dict, *args, **kwargs) -> Tuple[str, List[Any], Dict]:
        return model, messages, non_default_params

    async def async_get_chat_completion_prompt(self, model: str, messages: List[Any], non_default_params: Dict, *args, **kwargs) -> Tuple[str, List[Any], Dict]:
        return model, messages, non_default_params

    def get_custom_logger_for_prompt_management(self, *args, **kwargs): return None
    def get_router_model_id(self, *args, **kwargs): return None


def get_standard_logging_object_payload(*args, **kwargs):
    return None

def emit_standard_logging_payload(payload):
    if payload:
        emitter = get_emitter("plane.adapter")
        emitter.signal("LEGACY_LOG_EMITTED", payload=payload)

def get_standard_logging_metadata(*args, **kwargs):
    return {}

def scrub_sensitive_keys_in_metadata(litellm_params: Optional[dict] = None):
    return litellm_params or {}