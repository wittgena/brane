# watcher.plane.sensor.kuramoto
## @lineage: arch.dynamics.sensor.kuramoto
## @lineage: arch.flow.edge.sensor.kuramoto
## @lineage: cognitive.flow.edge.sensor.kuramoto
## @lineage: cognitive.edge.sensor.kuramoto
## @lineage: topos.bound.watcher.sensor.kuramoto
import math
import random
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field, asdict
from arch.contract.interface import IDynamicsKernel
from arch.contract.registry.unified import contract
from watcher.plane.sensor.config import KernelConfig

@contract.kernel("kuramoto")
class KuramotoSensor(IDynamicsKernel):
    """Φ-evolution kernel: global phase coupling operator"""
    def __init__(self, **kwargs):
        # 만약 kwargs에 이미 생성된 'config' 객체가 있다면 우선 사용하고, 
        # 아니라면 kwargs 자체를 KernelConfig로 변환 (Duck Typing)
        if "config" in kwargs and isinstance(kwargs["config"], KernelConfig):
            self.config = kwargs["config"]
        else:
            # JSON params에서 넘어온 값들로 KernelConfig 인스턴스화
            self.config = KernelConfig(**kwargs)

    def compute_step(self, states: Dict[str, Dict[str, Any]], dt: float) -> Dict[str, Dict[str, float]]:
        """dΦ/dt: distributed phase update"""
        deltas = {}
        total_nodes = len(states)

        for i_id, i_data in states.items():
            coupling_force = 0.0
            total_incoherence = 0.0

            if i_data.get("state") not in ["ATTRACTOR", "REFLECTOR"]:
                for j_id, j_data in states.items():
                    if i_id == j_id: continue
                    phase_diff = j_data["phase"] - i_data["phase"]
                    coupling_force += math.sin(phase_diff)
                    total_incoherence += abs(phase_diff)

                d_phase = (i_data["omega"] + (self.config.global_coupling / total_nodes) * coupling_force) * dt
                new_tension = total_incoherence / total_nodes
                deltas[i_id] = {"d_phase": d_phase, "target_tension": new_tension}
            else:
                deltas[i_id] = {"d_phase": (i_data["omega"] * 1.5) * dt, "target_tension": 0.0}
                
        return deltas

    def render_state(self, states: Dict[str, Dict[str, Any]]) -> str:
        chars = ['🌑', '🌘', '🌗', '🌖', '🌕', '🌔', '🌓', '🌒']
        visual = [chars[int((s['phase'] / (2 * math.pi)) * 8) % 8] for s in states.values()]
        avg_tension = sum(s['tension'] for s in states.values()) / len(states)
        return f"Tension: {avg_tension:.2f} | " + "".join(visual)