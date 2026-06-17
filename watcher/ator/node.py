# watcher.ator.node
## @lineage: surface.ator.node
## @lineage: xyz.surface.ator.node
## @lineage: xyz.subst.ator.node
## @lineage: foldbox.manager.workspace.ator
## @lineage: xyz.workspace.ator
## @lineage: xyz.field.ator
## @lineage: phase.watcher.field.ator
## @lineage: meta.watcher.field.ator
## @lineage: topos.watcher.field.ator
## @lineage: cognitive.watcher.field.ator
## @lineage: cognitive.field.ator
## @lineage: cognitive.node.ator
import math
import random
from typing import Dict, Any
from arch.contract.registry.unified import contract
from arch.contract.interface import IPhaseAtor, IPhaseField
from arch.proto.event.psi import PsiEvent, PsiCarrier

@contract.ator("node.ator")
class NodeAtor(IPhaseAtor):
    """
    @role: Kernel(AtorSensor)의 물리적 압력과 외부의 의미적 이벤트(Psi) 사이의 통역자
    """
    def __init__(self, **kwargs):
        self._id = kwargs.get("node_id", "unknown")
        self.initial_state = kwargs.get("initial_state", "NORMAL")
        self.tolerance_threshold = kwargs.get("tolerance_threshold", 8.0) # 인지 부조화 한계점

    @property
    def ator_id(self) -> str:
        return self._id

    @property
    def state(self) -> Dict[str, Any]:
        return {"status": self.initial_state}

    def set_state(self, new_state: str) -> None:
        pass

    async def react(self, event: PsiEvent, field: IPhaseField, bus: Any) -> None:
        """
        [의식의 발현 지점]
        Kernel이 계산한 무의식적 물리량(Tension)과 외부 자극(Event)을 융합합니다.
        """
        # 1. Field(공유 공간)에서 나와 타인들의 현재 물리 상태를 가져옴
        states = field.get_state()
        my_data = states.get(self.ator_id)
        if not my_data: return

        # --- A. [Kernel -> Ator] 물리량을 의미(Event)로 변환 ---
        # AtorSensor(Kernel)가 계산한 나의 인지 부조화(Tension)가 한계를 넘었을 때
        if my_data["tension"] >= self.tolerance_threshold:
            if my_data["state"] == "NORMAL":
                # 극심한 인지 부조화로 인해 극단주의자(REFLECTOR)로 변모하거나
                my_data["state"] = "REFLECTOR"
                my_data["phase"] += math.pi  # 위상을 완전히 반대로 뒤집음 (반발)
                
                # 비명(구조 요청) 이벤트를 글로벌 큐로 발행
                alert_carrier = PsiCarrier(kind="COGNITIVE_DISSONANCE", tag=self.ator_id, payload={})
                await bus.publish(PsiEvent(
                    event_id=event.event_id,
                    parent_id=event.event_id,
                    source_id=self.ator_id,
                    scope="GLOBAL",
                    tick=event.tick,
                    carrier=alert_carrier
                ))

        # --- B. [Ator -> Kernel] 의미(Event)를 물리량으로 변환 ---
        # 누군가가 강력한 의견(ATTRACT)을 담은 이벤트를 보냈을 때
        if event.carrier.kind == "ATTRACT_PHASE":
            target_phase = event.carrier.payload.get("phase", my_data["phase"])
            
            # 나의 현재 상태가 수용적(NORMAL)이라면, 물리적 위상(phase)을 그쪽으로 꺾음
            # -> 이 변화는 다음 틱(dt)에 AtorSensor(Kernel)의 compute_step에 반영되어
            # 군집(Clustering)의 인력을 완전히 바꿔놓게 됩니다.
            if my_data["state"] == "NORMAL":
                my_data["phase"] = target_phase