# watcher.plane.sensor.exchange
## @lineage: arch.dynamics.sensor.exchange
## @lineage: arch.flow.edge.sensor.exchange
## @lineage: cognitive.flow.edge.sensor.exchange
## @lineage: cognitive.edge.sensor.exchange
## @lineage: cognitive.edge.sensor.field
## @lineage: topos.bound.watcher.sensor.field
import math
import random
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field, asdict
from arch.contract.interface import IDynamicsKernel
from arch.contract.registry.unified import contract
from watcher.plane.sensor.config import KernelConfig

@contract.kernel("cognitive.exchange")
class ExchangeSensor(IDynamicsKernel):
    """
    @evo.sensor: Macroscopic Mean-Field Operator
    - Models the mechanism of 'Cognitive Surrender' and critical tension eruptions.
    - Tracks phase transitions triggered when local node topologies collide with  the macroscopic Mean-Field.
    """
    def __init__(self, **kwargs):
        if "config" in kwargs and isinstance(kwargs["config"], KernelConfig):
            self.config = kwargs["config"]
        else:
            self.config = KernelConfig(**kwargs)
            
        ## Phase Surrender Threshold: The critical boundary of topological stability for individual cognitive autonomy.
        self.surrender_threshold = kwargs.get("sync_threshold", 0.3)

    def compute_step(self, states: Dict[str, Dict[str, Any]], dt: float) -> Dict[str, Dict[str, float]]:
        deltas = {}
        total_nodes = len(states)
        
        ## Macroscopic Mean-Field Synthesis: Calculating the collective phase attractor
        avg_phase = sum(d["phase"] for d in states.values()) / total_nodes

        for i_id, i_data in states.items():
            if i_data.get("state") == "ATTRACTOR": 
                ## @anchor: Invariant manifolds that resist the global field to maintain absolute reference points
                deltas[i_id] = {"d_phase": i_data["omega"] * dt, "target_tension": 0.0}
                continue

            ## @topos.drift: Deviation between local node identity and the macroscopic field
            field_drift = avg_phase - i_data["phase"]
            
            ## @phase.collapse
            if abs(field_drift) > self.surrender_threshold:
                d_phase = (field_drift * self.config.global_coupling) * dt
                ## Ontological surrender results in the dissipation of cognitive dissonance (Tension)
                new_tension = 0.0 
            else:
                ## @phase.resistance
                d_phase = i_data["omega"] * dt
                new_tension = min(i_data["tension"] + abs(field_drift) * 0.1, 10.0)

            deltas[i_id] = {"d_phase": d_phase, "target_tension": new_tension}

        return deltas
    
    def render_state(self, states: Dict[str, Dict[str, Any]]) -> str:
        """@desc: Projects the continuous phase space onto discrete cognitive resonance metrics"""
        resonance = 0
        divergence = 0 
        visual = []

        for s in states.values():
            ## Map circular phase space to a linear projection axis [-1, 1]
            position = math.sin(s["phase"]) 
            
            if position > 0.5:
                visual.append('🟢') ## Positive Resonance
                resonance += 1
            elif position > 0:
                visual.append('↗️')
                resonance += 1
            elif position > -0.5:
                visual.append('↘️')
                divergence += 1
            else:
                visual.append('🔴') ## Negative Resonance
                divergence += 1
                
        ## @macroscopic.tension: Global cognitive fatigue or system flux
        avg_tension = sum(s['tension'] for s in states.values()) / len(states)
        field_regime = "RESONANT" if resonance > divergence else "DIVERGENT"
        
        status_bar = "".join(visual)
        return f"Flux(Tension): {avg_tension:.2f} | Sync({resonance:02d}:{divergence:02d}) [{field_regime}] | {status_bar}"