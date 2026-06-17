# arch.xor.manifold.flow
## @lineage: phase.dynamics.manifold.flow
## @lineage: arch.proto.manifold.flow
## @lineage: arch.model.manifold.flow
## @lineage: topos.model.manifold.flow
## @lineage: cognitive.dynamics.flow
## @lineage: cognitive.dynamics.manifold.flow
## @lineage: topos.dynamics.manifold.flow
"""@phase: Tension Accumulation $\rightarrow$ Projection $\rightarrow$ Collapse $\rightarrow$ Re-entry"""
import asyncio
import uuid
import time
import random
import json
from typing import Dict, Any, Optional
import redis.asyncio as redis_async
from arch.proto.event.psi import PsiEvent, PsiCarrier
from phase.dynamics.rhythm.bridge import RhythmBridge
from watcher.plane.surface import default_plane
from watcher.plane.emitter import get_emitter
from arch.xor.manifold.particle import ToposManifold, Particle

class TensionAccumulator(Particle):
    """@phase: Tension Accumulation (결핍 축적 및 자율 파열)"""
    def __init__(self, threshold=1.0, leakage=0.15, **kwargs):
        super().__init__(phase_name="TENSION_NODE", **kwargs)
        self.threshold = threshold
        self.leakage = leakage

    async def exist(self):
        while True:
            ## 텐션의 축적 (미세한 노이즈 포함)
            self.potential += self.leakage + random.uniform(-0.01, 0.01)
            if self.potential >= self.threshold:
                self.potential = 0.0
                pulse_id = f"beat.{uuid.uuid4().hex[:4]}"
                
                ## 이벤트 발행 후 해당 ID를 인과성(parent_id) 추적을 위해 큐에 함께 담음
                event = await self.emit_external(kind="PULSE", tag="TOPOS:TENSION_NODE", payload={"pulse_id": pulse_id})
                
                ## @phase: 다음 노드가 포화(불응기) 상태라면 억지로 밀어넣지 않고 에너지 소멸(Drop)
                try:
                    ToposManifold.void_gap.put_nowait({"id": pulse_id, "parent_id": event.event_id})
                    default_plane.record(time.time(), "TENSION_NODE", f"[♥] Pulse Fired: {pulse_id}", "SYS")
                except asyncio.QueueFull:
                    self.log.debug(f"Pulse {pulse_id} dropped (Refractory Period)")

                default_plane.record(time.time(), "TENSION_NODE", f"[♥] Pulse Fired: {pulse_id}", "SYS")
            await asyncio.sleep(0.1)

class PhaseProjector(Particle):
    async def exist(self):
        while True:
            data = await ToposManifold.void_gap.get()
            await asyncio.sleep(0.2) 
            
            vector_id = f"vector({data['id']})"
            event = await self.emit_external(
                kind="PROJECTION", tag="TOPOS:PROJECTOR", 
                payload={"vector_id": vector_id}, parent_id=data["parent_id"]
            )

            try:
                ToposManifold.projection_flow.put_nowait({"id": vector_id, "parent_id": event.event_id})
            except asyncio.QueueFull:
                pass

class ToposCollapse(Particle):
    """@phase: Collapse (위상 붕괴 및 결론 도출)"""
    async def exist(self):
        while True:
            data = await ToposManifold.projection_flow.get()
            await asyncio.sleep(0.4) 
            
            phi_id = f"Phi({uuid.uuid4().hex[:3]})"
            event = await self.emit_external(
                kind="COLLAPSE", tag="TOPOS:COLLAPSE", 
                payload={"phi_id": phi_id}, parent_id=data["parent_id"]
            )
            
            try:
                ToposManifold.collapse_field.put_nowait({"id": phi_id, "parent_id": event.event_id})
            except asyncio.QueueFull:
                pass
            default_plane.record(time.time(), "COLLAPSE", f"[♥] Contraction: {phi_id}", "INFO")

class ReentryInversion(Particle):
    """@phase: Inversion (여백 확보 및 재진입 준비)"""
    def __init__(self, bridge=None, **kwargs):
        phase_name = kwargs.pop("phase_name", "INVERSION") 
        super().__init__(phase_name=phase_name, bridge=bridge, **kwargs)
        self.reentry_multiplier = 1.0

    async def update_multiplier(self, new_multiplier: float):
        """@phase: 외부 자극에 의한 위상 반전 계수 재설정"""
        self.reentry_multiplier = new_multiplier
        self.log.info(f"[△] Re-entry multiplier updated to {self.reentry_multiplier}")

    async def exist(self):
        while True:
            data = await ToposManifold.collapse_field.get()
            await asyncio.sleep(0.3)

            ## [자동 조절 - 항상성 유지] - 현재 void_gap(초기 텐션 대기열)의 포화도를 측정
            current_tension = ToposManifold.void_gap.qsize()
            
            ## 진공 상태(0)일수록 에너지를 많이 뿜어내고, 포화 상태일수록 재진입 억제
            ## 예: 큐가 비어있으면 기본 3개의 reflow 생성, 큐가 3 이상이면 생성 0
            ## base_reflow = max(0, 3 - current_tension) 
            base_reflow = 5
            
            ## 외부 계수(multiplier)를 곱하여 최종 재진입 개수 확정
            actual_reflow = int(base_reflow * self.reentry_multiplier)

            for _ in range(actual_reflow):
                reflow_id = f"reflow.{uuid.uuid4().hex[:4]}"
                try:
                    ToposManifold.void_gap.put_nowait({"id": reflow_id, "parent_id": data["parent_id"]})
                except asyncio.QueueFull:
                    ## 큐가 가득 찼다면 즉시 잔여 재진입 에너지를 소멸시킴(Drop)
                    break 

            default_plane.record(
                time.time(), 
                "INVERSION", 
                f"[△] Inversion complete. Reflowed: {actual_reflow} (Tension: {current_tension})", 
                "SYS"
            )