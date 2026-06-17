# watcher.tracer.kernel
## @lineage: phase.watcher.tracer.kernel
## @lineage: meta.watcher.tracer.kernel
## @lineage: phase.receptor.tracer.kernel
## @lineage: cognitive.receptor.tracer.kernel
"""@flow: Environment(Sync) → SourceTracer(Membrane) → Ψ(PhaseSurface) → TraceKernel(Lens) → Rupture(emit)"""
import time
import asyncio
from datetime import datetime
from watchdog.events import FileSystemEventHandler
from typing import Dict, List
from phase.runtime.receptor.topos import ReceptorTopos
from watcher.tracer.trajectory import Point, WindowedTrajectory, DefaultBoundLensStrategy

class TracerKernel:
    """@desc: SourceTracer가 뿜어낸 파동(Ψ)을 스트리밍으로 받아 Lens(Φ')를 통해 실시간 위상 장력을 평가하고 붕괴를 판단"""
    def __init__(self, surface: ReceptorTopos, window_steps: int = 14, lens_preset: str = "kinematic"):
        self.surface = surface
        self.window_steps = window_steps
        self.lens = DefaultBoundLensStrategy(preset_name=lens_preset)
        self.trajectory_buffer: Dict[str, List[Point]] = {}

    async def watch_mutations(self):
        """SourceTracer로부터 유입되는 환경 변이를 구독"""
        async for msg in self.surface.sink.subscribe(self.surface.signal_channel):
            signal_id = msg.get("signal_id")
            value = msg.get("value")
            if signal_id and value is not None:
                await self._ingest_and_evaluate(signal_id, value)

    async def _ingest_and_evaluate(self, signal_id: str, current_value: float):
        if signal_id not in self.trajectory_buffer:
            self.trajectory_buffer[signal_id] = []
            
        buffer = self.trajectory_buffer[signal_id]
        buffer.append(Point(timestamp=datetime.now(), value=current_value))
        
        # 시간에 따른 망각 (Sliding Window)
        if len(buffer) > self.window_steps:
            buffer.pop(0)
            
        if len(buffer) < self.window_steps:
            return

        # 윈도우 생성 및 렌즈 투영
        window = WindowedTrajectory(
            identity=signal_id,
            start_time=buffer[0].timestamp,
            end_time=buffer[-1].timestamp,
            points=buffer
        )
        
        scan_result = self.lens.scan(window)
        if scan_result["status"] != "valid":
            return

        metrics = scan_result["metrics"]

        # 파열 조건: 예를 들어 변이 빈도(trend)가 급증하거나 변동성(volatility)이 폭발할 때
        is_ruptured = metrics.get("trend", 0) > 0.8 or metrics.get("volatility", 0) >= 0.05
        
        if is_ruptured:
            print(f"\n⚠️ [TraceKernel] System Tension Rupture: '{signal_id}' is unstable!")
            
            trace_record = {
                "signal": signal_id,
                "metrics": metrics,
                "timestamp": datetime.now().isoformat()
            }
            # 과거 FieldKernel의 단순했던 apply_inversion()을 
            # 고차원적인 데이터와 함께 재발행(Reflect)하는 것으로 승격
            await self.surface.emit_psi("xphi_structure_event", payload=trace_record)

    async def watch_psi_feedback(self):
        """시스템 재진입(Re-entry) 궤적 감시 (기존 FieldKernel 기능 흡수)"""
        async for msg in self.surface.sink.subscribe(self.surface.psi_channel):
            print(f"🌀 [TraceKernel] Re-entry Ψ′ feedback → {msg}")

    async def start_daemons(self):
        """데몬 부트스트랩"""
        asyncio.create_task(self.watch_mutations())
        asyncio.create_task(self.watch_psi_feedback())