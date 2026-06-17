# phase.dynamics.rhythm.receptor
## @lineage: phase.reflect.rhythm.receptor
## @lineage: cognitive.reflect.rhythm.receptor
## @lineage: cognitive.rhythm.receptor
## @lineage: cognitive.rhythm.receptor.aura
import math
from dataclasses import dataclass, field
from typing import Any, Optional
from watcher.plane.emitter import get_emitter
from phase.dynamics.rhythm.psi import RhythmPsi, RhythmSignature

log = get_emitter("rhythm.receptor")

class RhythmReceptor:
    def __init__(self, name: str, own_signature: RhythmSignature, rupture_threshold: float = 1.0):
        self.name = name
        self.own_signature = own_signature
        self.rupture_threshold = rupture_threshold
        self.current_tension = 0.0  # 누적된 압력

    def absorb(self, wave: RhythmPsi):
        ## 수신자의 구조와 발신자의 구조가 얼마나 공명하는가?
        resonance_coeff = self.own_signature.resonance_with(wave.signature)
        
        ## 실제 시스템에 가해지는 유효 타격량 = 원래 강도 * 공명 계수
        impact = wave.intensity * resonance_coeff
        self.current_tension += impact
        log.info(
            f"[{self.name}] Absorbed Wave from {wave.origin_id} | "
            f"Resonance: {resonance_coeff:.2f} | Impact: {impact:.2f} | "
            f"Tension: {self.current_tension:.2f}/{self.rupture_threshold}"
        )

        ## 임계점(Threshold) 도파 시 상전이(Rupture) 격발
        if self.current_tension >= self.rupture_threshold:
            self._rupture(wave.residue)

    def _rupture(self, trigger_residue: Any):
        """상전이(Phase Transition): 쌓인 텐션을 방출하고 상태를 붕괴"""
        log.warning(f"## @rupture: {self.name} Phase Transition Triggered!")
        self._on_transition(trigger_residue)
        self.current_tension = 0.0

    def _on_transition(self, residue: Any):
        ## Override to define specific rupture behaviors
        log.info(f" -> Reorganizing attractor based on residue: {residue}")

if __name__ == "__main__":
    ## 수신 노드(관찰자) 생성: 차원 3, 밀도 0.5의 구조를 가짐
    analyzer_node = RhythmReceptor(
        name="L3:AnalyzerState",
        own_signature=RhythmSignature(dimension=3, density=0.5, is_closed=True),
        rupture_threshold=2.0 # 텐션이 2.0이 되면 파열
    )

    ## 매질에 던져지는 파동들 (타입이 없습니다)
    waves = [
        ## 구조가 전혀 다른 곳에서 온 약한 파동 (공명 낮음)
        RhythmPsi(
            origin_id="L0:PrimitiveUtils",
            intensity=1.0,
            signature=RhythmSignature(dimension=1, density=0.1, is_closed=False)
        ),
        ## 구조가 완전히 동일한 곳에서 온 중간 파동 (공명 100%)
        RhythmPsi(
            origin_id="L3:ToposBounder",
            intensity=1.5,
            signature=RhythmSignature(dimension=3, density=0.5, is_closed=True),
            residue="[xe: Unresolved Graph Leakage]"
        )
    ]

    ## 매질의 전달 (EventBus가 매질에 파동을 뿌림)
    for w in waves:
        analyzer_node.absorb(w)