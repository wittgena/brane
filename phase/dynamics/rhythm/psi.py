# phase.dynamics.rhythm.psi
## @lineage: phase.reflect.rhythm.psi
## @lineage: cognitive.reflect.rhythm.psi
## @lineage: cognitive.rhythm.psi
## @lineage: cognitive.context.aura.psi
import math
from dataclasses import dataclass, field
from typing import Any, Optional
from watcher.plane.emitter import get_emitter

log = get_emitter("rhythm.psi")

@dataclass(frozen=True)
class RhythmSignature:
    dimension: int     
    density: float  
    is_closed: bool   

    def resonance_with(self, other: 'ToposSignature') -> float:
        dim_diff = abs(self.dimension - other.dimension)
        den_diff = abs(self.density - other.density)
        
        ## 차원과 밀도의 차이가 적을수록 공명률 상승 (임의의 감쇠 함수)
        resonance = math.exp(-(dim_diff + den_diff))
        
        ## 둘 다 닫힌 계이거나 열린 계이면 공명 증폭
        if self.is_closed == other.is_closed:
            resonance = min(1.0, resonance * 1.2)
            
        return resonance

@dataclass(frozen=True)
class RhythmPsi:
    origin_id: str                 # 발신지 식별자 (로깅용)
    intensity: float                # 파동의 강도 (0.0 ~ 무한대)
    signature: RhythmSignature      # 발신지의 위상 구조
    residue: Any = None            # 튕겨져 나온 데이터 잔여물 (xe)