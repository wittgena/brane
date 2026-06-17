# watcher.kernel.inversion
## @lineage: phase.watcher.kernel.inversion
## @lineage: meta.watcher.kernel.inversion
from typing import List, Dict, Optional, Any
from arch.contract.registry.unified import contract
from arch.contract.interface import ICriticalDetector, IPhaseField
from arch.proto.event.psi import PsiEvent, PsiCarrier

@contract.watcher("inversion.watcher")
class InversionWatcher(ICriticalDetector):
    """
    @role: Field의 Pressure(피로도) 가속도를 감시, 망델브로 경계(최고점, dS/dt=0)에 도달하는 순간 파열(Rupture) 대신 역-반전(Inversion) 댐핑을 주입
    """
    def __init__(self, **kwargs):
        self.peak_threshold = kwargs.get("peak_threshold", 353.0)
        self.anchor_target = kwargs.get("anchor_target", 5.0)
        
        ## The Observer's Memory
        self.last_pressure = 0.0
        self.last_dp = 0.0

    def extract(self, field: IPhaseField) -> Dict[str, float]:
        return {"pressure": getattr(field, "pressure", 0.0)}

    def evaluate(self, field: IPhaseField, history: List[Any], current_tick: int) -> Optional[PsiEvent]:
        metrics = self.extract(field)
        current_pressure = metrics.get("pressure", 0.0)

        ## 1차 미분(속도)과 2차 미분(가속도) 계산
        dp = current_pressure - self.last_pressure
        ddp = dp - self.last_dp

        ## 상태 업데이트
        self.last_pressure = current_pressure
        self.last_dp = dp

        ## 망델브로 경계면 판별: 압력이 높고, 팽창 속도(dp)가 꺾여 0에 수렴하는 극대점 (dS/dt ≈ 0)
        is_peak_reached = (current_pressure >= self.peak_threshold) and (dp <= 0.01) and (ddp < 0)

        if is_peak_reached:
            expected = current_pressure - self.anchor_target
            carrier = PsiCarrier(
                kind="INVERSION", 
                tag="ARBITRAGE_SETTLEMENT", 
                payload={
                    "peak_tension": current_pressure,
                    "target": self.anchor_target,
                    "expected_yield": expected
                }
            )
            
            return PsiEvent(
                event_id=f"isorhesis-inversion-{current_tick}",
                parent_id=None,
                source_id="watcher.inversion",
                scope="GLOBAL",
                tick=current_tick,
                carrier=carrier,
                context={"state": "damping_injected", "action": "execute_bridge_tx"}
            )
        return None