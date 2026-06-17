# watcher.plane.sensor.ator
## @lineage: arch.dynamics.sensor.ator
## @lineage: arch.flow.edge.sensor.ator
## @lineage: cognitive.flow.edge.sensor.ator
## @lineage: cognitive.edge.sensor.ator
## @lineage: topos.bound.watcher.sensor.ator
import math
import random
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field, asdict
from arch.contract.interface import IDynamicsKernel
from arch.contract.registry.unified import contract
from watcher.plane.sensor.config import KernelConfig

@contract.kernel("ator")
class AtorSensor(IDynamicsKernel):
    """Φ-evolution kernel: Multi-Ator Cognitive Consensus & Clustering"""
    def __init__(self, **kwargs):
        if "config" in kwargs and isinstance(kwargs["config"], KernelConfig):
            self.config = kwargs["config"]
        else:
            self.config = KernelConfig(**kwargs)
            
        ## AtorSensor 전용 추가 파라미터도 kwargs에서 추출 (기본값 부여)
        self.trust_radius = kwargs.get("trust_radius", 1.0)
        self.repulsion_factor = kwargs.get("repulsion_factor", 0.2)

    def compute_step(self, states: Dict[str, Dict[str, Any]], dt: float) -> Dict[str, Dict[str, float]]:
        deltas = {}
        total_nodes = len(states)

        for i_id, i_data in states.items():
            if i_data.get("state") in ["ATTRACTOR", "REFLECTOR"]:
                # 확신에 찬 에이전트(Attractor)는 주변을 끌어당기기만 하고 자신은 변하지 않음
                deltas[i_id] = {"d_phase": (i_data["omega"] * 0.1) * dt, "target_tension": 0.0}
                continue

            consensus_force = 0.0
            cognitive_dissonance = 0.0

            for j_id, j_data in states.items():
                if i_id == j_id: continue
                
                # 가설(Phase)의 차이 계산 (최단 경로)
                diff = (j_data["phase"] - i_data["phase"] + math.pi) % (2 * math.pi) - math.pi
                distance = abs(diff)

                if distance < self.trust_radius:
                    # 의견이 비슷하면 서로 동화됨 (수렴)
                    consensus_force += math.sin(diff) * self.config.global_coupling
                else:
                    # 의견이 너무 다르면 서로를 밀어냄 (양극화/파벌 형성)
                    consensus_force -= math.sin(diff) * self.repulsion_factor
                    cognitive_dissonance += distance # 이해할 수 없는 의견이 많을수록 긴장도 급증

            d_phase = (i_data["omega"] + (consensus_force / total_nodes)) * dt
            new_tension = min(cognitive_dissonance / total_nodes, 10.0)

            deltas[i_id] = {"d_phase": d_phase, "target_tension": new_tension}

        return deltas

    def render_state(self, states: Dict[str, Dict[str, Any]]) -> str:
        """가설의 군집화(Clustering) 상태를 시각화"""
        # 위상을 4가지 주요 '가설(A, B, C, D)'로 매핑
        hypotheses = ['🟦', '🟩', '🟨', '🟥']
        visual = [hypotheses[int((s['phase'] / (2 * math.pi)) * 4) % 4] for s in states.values()]
        avg_tension = sum(s['tension'] for s in states.values()) / len(states)
        status_bar = "".join(visual)
        return f"Dissonance: {avg_tension:.2f} | {status_bar}"