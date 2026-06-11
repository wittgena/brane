# channel.bound.plane
from typing import Any, Dict, List, Optional
from gate.model.types.utils import LiteLLMLoggingBaseClass
from channel.cost.telemetry import Telemetry
from channel.cost.laminar import start_active_span, end_active_span
from meta.watcher.tracker.conv.metrics import Metrics

class Logging(LiteLLMLoggingBaseClass):
    """
    구조 전환을 위한 어댑터 클래스입니다.
    기존 호출 구조를 유지하면서 내부적으로는 새로운 시스템(Telemetry/Laminar)을 호출합니다.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Telemetry 모듈이 실질적인 비용/Latency 계산 담당
        self._telemetry = Telemetry(model_name=kwargs.get("model", "unknown"), metrics=Metrics())
        self._telemetry.on_request(telemetry_ctx=kwargs)

    def success_handler(self, result=None, **kwargs):
        # 성공 시 로직을 새 Telemetry 모듈로 위임
        if result:
            self._telemetry.on_response(result)
        super().success_handler(result, **kwargs)

    def failure_handler(self, exception, *args, **kwargs):
        # 실패 시 로직 위임
        self._telemetry.on_error(exception)
        return super().failure_handler(exception, *args, **kwargs)

    # ... 나머지 메서드들은 pass 혹은 부모 호출 ...

# 전역 유틸리티 함수들도 새로운 시스템으로 매핑
def get_standard_logging_object_payload(*args, **kwargs):
    # 이제 이 Payload는 굳이 조립하지 말고 None을 반환하거나,
    # 필요하다면 Telemetry 내부의 데이터를 가져오도록 연결
    return None 

def emit_standard_logging_payload(payload):
    # 기존 로거 대신 emitter를 사용하도록 변경
    from watcher.plane.emitter import get_emitter
    emitter = get_emitter("plane.adapter")
    emitter.signal("LEGACY_LOG_EMITTED", payload=payload)