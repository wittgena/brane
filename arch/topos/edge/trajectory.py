# arch.topos.edge.trajectory
## @lineage: phase.dynamics.edge.trajectory
## @lineage: arch.dynamics.edge.trajectory
## @lineage: arch.flow.edge.trajectory
## @lineage: cognitive.flow.edge.trajectory
## @lineage: cognitive.edge.trajectory
## @lineage: foldbox.trace.trajectory
import json
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set
from watcher.plane.emitter import get_logger

log = get_logger("edge.trajectory")

@dataclass
class ClosureDelta:
    """기호적/구조적 변이 규칙 (Δ)"""
    lineage_ref: Optional[str] = None
    tension_level: float = 0.0
    break_symbols: Set[str] = field(default_factory=set)
    align_symbols: Set[str] = field(default_factory=set)
    bias_shift: float = 0.0

@dataclass(kw_only=True)
class SignatureBound:
    """위상 공간 (Φ) - Lineage 기반 폐쇄성 관리"""
    module_id: str
    base_instructions: str
    input_fields: List[str]
    output_fields: List[str]

    ref_topo: int = 0 
    ref_press: int = 0
    
    active_repulsion: Dict[str, float] = field(default_factory=dict)
    active_attraction: Dict[str, float] = field(default_factory=dict)

    lineage: List[str] = field(default_factory=list)
    delta_history: List[ClosureDelta] = field(default_factory=list)
    version: int = 1

    def mutate(self, rule: ClosureDelta):
        """Φ -> Φ⁺: 감쇄와 강화를 통한 위상적 안정화"""
        self.delta_history.append(rule)
        strength = rule.tension_level + rule.bias_shift
        
        for sym in rule.break_symbols:
            self.active_repulsion[sym] = self.active_repulsion.get(sym, 0.0) + strength
            
        for sym in rule.align_symbols:
            self.active_attraction[sym] = self.active_attraction.get(sym, 0.0) + strength

        decay_factor = 0.9
        self._apply_decay(self.active_repulsion, decay_factor)
        self._apply_decay(self.active_attraction, decay_factor)

        if rule.lineage_ref and rule.lineage_ref not in self.lineage:
            self.lineage.append(rule.lineage_ref)

        self.version += 1
        log.info(f"[{self.module_id}] Field Stabilized v{self.version} (Lineage: {rule.lineage_ref})")

    def _apply_decay(self, field_map: Dict[str, float], factor: float):
        for k in list(field_map.keys()):
            field_map[k] *= factor
            if field_map[k] < 0.05:
                del field_map[k]

    def dump_state(self) -> dict:
        return {
            "module_id": self.module_id,
            "version": self.version,
            "lineage": self.lineage,
            "repulsion_field": self.active_repulsion,
            "attraction_field": self.active_attraction
        }

class TrajectoryXor:
    def __init__(self, tension_threshold: float = 0.5):
        self.tension_threshold = tension_threshold

    def synth(self, recent_bases: List[Dict]) -> Optional[ClosureDelta]:
        if not recent_bases: return None

        bad_symbols, env_symbols = set(), set()
        max_tension = 0.0
        ref_lineage = recent_bases[0].get("lineage", ["unknown"])[-1]

        for basis in recent_bases:
            traces = basis.get("traces", [])
            for t in traces:
                # [핵심 수정] score 조건 완전 삭제. 들어오는 모든 궤적에서 무조건 기호를 추출.
                for step in t.get("steps", []):
                    payload = str(step.get("inputs", {}).get("payload", ""))
                    tokens = {word.lower() for word in payload.split() if len(word) > 3}
                    bad_symbols.update(tokens)

            context = basis.get("context", {})
            tension = context.get("tension", 0.0)
            if tension > max_tension: max_tension = tension
            if tension > self.tension_threshold:
                for doc in context.get("enriched_docs", []):
                    for kw, count in doc.get("keywords", []):
                        env_symbols.add(kw)

        return ClosureDelta(
            lineage_ref=ref_lineage,
            tension_level=max_tension,
            break_symbols=bad_symbols - env_symbols,
            align_symbols=env_symbols,
            bias_shift=max_tension * 0.1
        )