# arch.xor.manifold.particle
"""@phase: Tension Accumulation -> Projection -> Collapse -> Re-entry"""
import asyncio
import uuid
import time
from typing import Dict, Any, Optional, Set
from arch.proto.event.psi import PsiEvent, PsiCarrier
from watcher.plane.emitter import get_emitter

class ToposManifold(type):
    """
    @registry: Track all active topological nodes for phase perturbation
    @flow: tension_rupture -> projection -> collapse -> inversion/re-entry
    """
    MAX_LIMIT = 50
    _semaphore: Optional[asyncio.Semaphore] = None
    _instances: list = [] 
    _active_tasks: set[asyncio.Task] = set()

    void_gap: Optional[asyncio.Queue] = None      
    projection_flow: Optional[asyncio.Queue] = None  
    collapse_field: Optional[asyncio.Queue] = None
    psi_queue: Optional[asyncio.Queue] = None

    global_tick: int = 0
    _tick_lock: Optional[asyncio.Lock] = None

    @classmethod
    def ignite_manifold(mcs):
        """이벤트 루프가 시작된 직후(main 함수 내부) 최초 1회 호출"""
        if mcs.void_gap is None:
            mcs.void_gap = asyncio.Queue()
            mcs.projection_flow = asyncio.Queue()
            mcs.collapse_field = asyncio.Queue()
            mcs.psi_queue = asyncio.Queue()
            mcs._semaphore = asyncio.Semaphore(mcs.MAX_LIMIT)
            mcs._tick_lock = asyncio.Lock()
            get_emitter("manifold", phase="TOPOS").info("ToposManifold Ignited: Quantums initialized.")

    def __call__(cls, *args, **kwargs):
        instance = super().__call__(*args, **kwargs)
        ToposManifold._instances.append(instance)
        
        ## 시스템 점화 확인 (Safety Net)
        if cls.void_gap is None:
            raise RuntimeError("ToposManifold.ignite_manifold() must be called inside the event loop before creating particles.")

        async def managed_exist():
            async with cls._semaphore:
                try:
                    await instance.exist()
                except asyncio.CancelledError:
                    instance.log.info("[Phase] Particle existence cancelled gracefully.")
                except Exception as e:
                    instance.log.error(f"[Phase] Particle collapse due to anomaly: {e}")
                finally:
                    if instance in ToposManifold._instances:
                        ToposManifold._instances.remove(instance)

        ## Task 강한 참조 유지 및 완료 시 제거 콜백 등록
        task = asyncio.create_task(managed_exist())
        ToposManifold._active_tasks.add(task)
        task.add_done_callback(ToposManifold._active_tasks.discard)
        return instance

class Particle(metaclass=ToposManifold):
    """@scale: cellular-unit (위상 잔여물 및 기본 노드)"""
    def __init__(self, phase_name="TOPOS", bridge=None):
        self.trace_id = f"{self.__class__.__name__}.{uuid.uuid4().hex[:4]}"
        self.bridge = bridge
        self.log = get_emitter(self.trace_id, phase=phase_name)
        self.potential = 0.0

    async def shock_reset(self):
        """@phase: phase reset (Defibrillation)"""
        self.potential = 0.0
        self.log.warn(f"[⚡] Shock applied: Phase reset for {self.trace_id}")

    async def emit_external(self, kind: str, tag: str, payload: dict = None, parent_id: str = None) -> PsiEvent:
        """@phase: transduction (Internal -> External)"""
        # [수정] 원자적(Atomic) 틱 증가 보장
        async with ToposManifold._tick_lock:
            ToposManifold.global_tick += 1
            current_tick = ToposManifold.global_tick

        carrier = PsiCarrier(kind=kind, tag=tag, payload=payload or {"timestamp": time.time()})
        event = PsiEvent(
            event_id=f"evt-{uuid.uuid4().hex[:6]}",
            parent_id=parent_id,
            source_id=self.trace_id,
            scope="GLOBAL",
            tick=current_tick,
            carrier=carrier,
            context={"domain": "toposbeat", "phase": "rhythm"}
        )
        if self.bridge:
            await self.bridge.emit(event)
        return event

    async def exist(self):
        """Subclasses must implement this topological heartbeat."""
        pass