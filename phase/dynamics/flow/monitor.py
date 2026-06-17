# phase.dynamics.flow.monitor
"""
@flow: Ψ(Runtime Context) → Inspect → Φ(Adaptive Wrapper) → Direct/Intercept
@intent: Ator 비동기 큐 엔진과 동기식 테스트 환경(unittest) 모두에서 주석 명세(@phase, @flow, @invariant)를 인지하고 위상 상태를 동기화하는 범용 어댑티브 모니터
"""
import sys
import asyncio
import re
import inspect
import functools
from pathlib import Path
from typing import Any, Callable
from watcher.plane.emitter import get_logger, get_emitter
from arch.proto.phase.flow import PhaseFlow, FlowState

log = get_logger("flow.monitor")
monitor_emitter = get_emitter("flow.monitor", phase="observe", boundary="telemetry")

def flow_monitor(func: Callable) -> Callable:
    """
    @role: Adaptive Phase-Field Observer
    대상 메서드의 docstring 및 인자를 동적으로 분석하여 환경에 맞게 런타임 흐름을 감시
    - AtorRuntime 내부: ctx.state["boundary"] 제어를 통한 우아한 위상 전이 유도
    - Unittest / 일반 환경: 글로벌 에미터를 통한 위상 텔레메트리 방출 및 네이티브 예외 전파
    """
    ## 대상 함수의 메타데이터 및 실행 환경 판별
    is_coroutine = inspect.iscoroutinefunction(func)
    
    @functools.wraps(func)
    def sync_wrapper(self, *args, **kwargs):
        _monitor_enter(func, self)
        try:
            result = func(self, *args, **kwargs)
            return result
        except Exception as e:
            return _monitor_fracture(e, func, args, kwargs)

    @functools.wraps(func)
    async def async_wrapper(self, *args, **kwargs):
        _monitor_enter(func, self)
        try:
            result = await func(self, *args, **kwargs)
            return result
        except Exception as e:
            return _monitor_fracture(e, func, args, kwargs)

    return async_wrapper if is_coroutine else sync_wrapper


def _monitor_enter(func: Callable, instance: Any):
    """함수 진입 시점에 주석 구조(@phase, @flow, @invariant)를 추출하여 관측 로그를 남깁니다."""
    docstring = func.__doc__ or ""
    
    ## 클래스명.메서드명 형태로 오퍼레이터 식별자 추출
    class_name = getattr(instance, "__class__", instance).__name__
    op_id = f"{class_name}.{func.__name__}"
    
    ## 위상 지향 주석 패턴 매칭
    flow_match = re.search(r'@flow:\s*(.+)', docstring)
    phase_match = re.search(r'@phase(?:\.\w+)?:\s*(.+)', docstring)
    invariant_match = re.search(r'@invariant:\s*(.+)', docstring)
    
    ## 추출된 명세 로깅 체계 정합화
    if flow_match or phase_match or invariant_match:
        f_val = flow_match.group(1).strip() if flow_match else "Implicit"
        p_val = phase_match.group(1).strip() if phase_match else "Implicit"
        log.info(f"[Φ:Observe] {op_id} | Phase: [{p_val}] | Flow: [{f_val}]")
        
        if invariant_match:
            log.debug(f"  -> Invariant Spec Check: {invariant_match.group(1).strip()}")


def _monitor_fracture(e: Exception, func: Callable, args: tuple, kwargs: dict) -> Any:
    """물리적 예외 발생 시, 컨텍스트를 판별하여 위상 분할(Fracture) 메커니즘을 유연하게 처리"""
    class_name = args[0].__class__.__name__ if args else "Global"
    op_id = f"{class_name}.{func.__name__}"
    
    log.error(f"[Φ:Fracture] '{op_id}' 내부 균열 감지. 원인: {e}")

    ## 인자 더미에서 AtorRuntime이 사용하는 FlowState(ctx)와 ProtoFlow 객체가 있는지 탐색
    ctx: FlowState = next((arg for arg in args if isinstance(arg, FlowState)), None)
    flow: PhaseFlow = next((arg for arg in args if isinstance(arg, PhaseFlow)), None)
    
    ## AtorRuntime 제어 하에 비동기 큐로 구동 중인 프로덕션 환경인 경우
    if ctx is not None:
        log.warning(f"  -> Ator 런타임 컨텍스트 확인 -> 위상 공간 균열을 주입")
        ctx.state["boundary"] = "fracture"
        ctx.state["fracture_reason"] = str(e)
        return flow
        
    else:
        log.warning(f"  -> 독립 실행/테스트 환경 확인. 전역 평면(SurfacePlane)으로 텔레메트리 방출 후 예외를 전파")
        ## 글로벌 위상장에 붕괴 신호 송신
        monitor_emitter.crit(
            f"unhandled_fracture:{op_id}", 
            payload={"exception": type(e).__name__, "message": str(e)}
        )
        ## 네이티브 예외를 다시 throw
        raise e
