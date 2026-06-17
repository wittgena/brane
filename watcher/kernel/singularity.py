# watcher.kernel.singularity
## @lineage: phase.watcher.kernel.singularity
## @lineage: meta.watcher.kernel.singularity
from typing import List, Dict, Optional, Any
from arch.contract.registry.unified import contract
from arch.contract.interface import ICriticalDetector, IPhaseField
from arch.proto.event.psi import PsiEvent, PsiCarrier

@contract.watcher("singularity.watcher")
class SingularityWatcher(ICriticalDetector):
    """@role: Field의 Pressure(피로도)를 감시하다가 임계치를 넘으면 파열(Rupture) 이벤트를 발생"""
    def __init__(self, **kwargs):
        self.candidate_limit = kwargs.get("candidate_limit", 10.0)
        self.rupture_limit = kwargs.get("rupture_limit", 25.0)

    def extract(self, field: IPhaseField) -> Dict[str, float]:
        return {"pressure": getattr(field, "pressure", 0.0)}

    def evaluate(self, field: IPhaseField, history: List[Any], current_tick: int) -> Optional[PsiEvent]:
        metrics = self.extract(field)
        pressure = metrics.get("pressure", 0.0)

        # 압력이 임계치를 초과하면 붕괴(Rupture) 트리거 발동
        if pressure >= self.rupture_limit:
            carrier = PsiCarrier(kind="RUPTURE", tag="CRITICAL", payload={"pressure": pressure})
            return PsiEvent(
                event_id="system-rupture",
                parent_id=None,
                source_id="watcher.singularity",
                scope="GLOBAL",
                tick=current_tick,
                carrier=carrier,
                context={"state": "collapse"}
            )
        return None