# phase.runtime.receptor.topos
## @lineage: phase.receptor.topos
## @lineage: cognitive.receptor.topos
import time
import json
from typing import Optional, Dict
from phase.runtime.surface.sink import EmitterSink
from watcher.plane.emitter import get_emitter

log = get_emitter("receptor.topos")

class ReceptorTopos:
    """@role: ∂Φ bound surface (Domain Layer) - 인프라(Redis, File, API)는 EmitterSink로 추상화되어 주입됨."""
    def __init__(self, sink: EmitterSink):
        self.sink = sink
        self.state_key = "meta.self:state:current_phase"
        self.signal_channel = "meta.self:signals:phase_mutation"
        self.psi_channel = "meta.self:signals:psi"

    async def get_current_phase(self) -> str:
        val = await self.sink.get_control_flag(self.state_key)
        return val or "Φ0"

    async def set_phase(self, phase: str):
        await self.sink.set(self.state_key, phase)

    async def emit_psi(self, event_type: str, weight: int = 1, payload: Optional[Dict] = None):
        """@desc: 외부의 파동(payload)을 수용하여 내부의 위상 좌표와 병합한 뒤 전파"""
        ## Source에서 전달받은 파동 데이터 수용 (원본 보호를 위해 복사)
        merged_payload = payload.copy() if payload else {}
        
        ## Surface의 절대 좌표(event, ts 등) 강제 덮어쓰기 병합
        merged_payload.update({
            "event": event_type,
            "weight": weight,
            "ts": time.time()
        })
        print(f"Ψ emit → {merged_payload}")
        await self.sink.publish(self.psi_channel, json.dumps(merged_payload))