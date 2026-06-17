# arch.xor.judger
## @lineage: hub.xor.judger
import time
from typing import List, Tuple
from dataclasses import dataclass, field
from watcher.plane.emitter import get_emitter

log = get_emitter("xor.judger")

@dataclass
class Signal:
    """Ψ: 단순 텍스트가 아닌, 시스템 내부에서 전파되는 파동(Wave)"""
    source: str
    pressure: float
    frequency: str
    payload: str
    timestamp: float = field(default_factory=time.time)

@dataclass
class Residue:
    """xe: 구조적 정합에 실패한 구체적 파편(Rupture)"""
    topos_path: str
    dissonance_type: str
    content: str

class JudgmentField:
    """Φ': 신호들이 간섭하며 형성되는 연속적인 장"""
    def __init__(self):
        self.potential_energy = 0.0
        self.interference_pattern = [] 
        self.stable_projection = None

    def update_field(self, signal: Signal, xe_list: List[Residue]):
        self.potential_energy += signal.pressure * (1.0 + len(xe_list))
        self.interference_pattern.append({
            "t": signal.timestamp,
            "energy": self.potential_energy,
            "ruptures": [r.dissonance_type for r in xe_list]
        })

class PureJudger:
    """
    [Pure State Machine]
    루프 제어권과 LLM 의존성을 외부로 반환하고, 
    오직 장(Field)의 상태 변화와 안정화(Attractor) 판정만 수행하는 코어 엔진.
    """
    def __init__(self):
        self.phi_prime = JudgmentField()
        self.memory_path = []

    def integrate(self, signal: Signal, xe_list: List[Residue], cycle: int) -> Tuple[bool, str]:
        """외부에서 관측된 신호와 파편을 장에 투영하고 안정화 여부(재진입 여부) 반환"""
        self.phi_prime.update_field(signal, xe_list)
        self.memory_path.extend(xe_list)
        
        # 에너지가 임계치 이하로 떨어지거나 루프가 포화되면 중단 (Attractor 도달)
        is_stable = len(xe_list) == 0 or cycle >= 5
        
        if is_stable:
            log.info(f"Attractor Reached at Cycle {cycle}. Field Energy: {self.phi_prime.potential_energy}")
            return False, "" # 루프 중단
        
        # xe(잔여)가 다음 사이클의 압력(re-entry payload)이 됨
        reentry_payload = f"Tension from {len(xe_list)} residues: {[r.content for r in xe_list]}"
        return True, reentry_payload

    def get_projection(self):
        return {"state": "evolving", "energy": self.phi_prime.potential_energy}