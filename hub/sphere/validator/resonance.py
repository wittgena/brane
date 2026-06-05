# hub.sphere.validator.resonance
import asyncio
import inspect
from pathlib import Path
from typing import Any, Dict
from arch.proto.phase.flow import ProtoFlow, FlowState, Transduction, Resonance, Judgment, Align
from arch.contract.registry.unified import contract
from watcher.plane.emitter import get_logger

log = get_logger('resonance.validator')

@contract.ator("resonance.validator")
class ResonanceValidator(Resonance):
    """
    @role: 위상 정합성 검사기 (Topology Harmony Validator)
    @flow: Ψ_gen(PHI) ⊕ Ψ_rules(Static) → Δ(Status)
    """
    def interfere(self, gen_payload: Any, crit_payload: Any) -> Dict[str, Any]:
        ## 1. 대상 위상 추출 (보통 gen_payload에 SCRIPT/AUG가 담김)
        topology = gen_payload.get("topology") or gen_payload
        if not isinstance(topology, dict):
            return {"status": "retry", "payload": {"feedback": "Invalid AUG format: Expected dict"}}

        errors = []
        node_ids = set(topology.keys())
        
        ## 2. 위상 정적 검증 (Static Interference)
        for node_id, config in topology.items():
            spec = config.get("spec", {})
            
            ## (A) 구조적 필수 요소 체크
            if "type" not in config or "spec" not in config:
                errors.append(f"Node '{node_id}' is missing 'type' or 'spec'")
                continue

            ## (B) 참조 무결성 (Broken Link) 체크
            nxt = spec.get("next")
            if nxt and nxt not in node_ids and nxt != "UGA":
                errors.append(f"Node '{node_id}' points to non-existent next node: '{nxt}'")

            ## (C) Judgment 규칙 체크
            if config.get("type") == "judgement":
                rules = spec.get("rules", {})
                if not rules:
                    errors.append(f"judgment '{node_id}' has no rules")
                for state, target in rules.items():
                    if target not in node_ids and target != "UGA":
                        errors.append(f"Judgment '{node_id}' rule '{state}' target '{target}' is missing")

        ## 간섭 결과에 따른 위상 결정 (Decision)
        if errors:
            log.warning(f"  [Resonance] Dissonance detected in AUG: {len(errors)} errors found.")
            return {
                "status": "retry", 
                "payload": {
                    "feedback": "AUG Topology is fractured. Correct the following inconsistencies.",
                    "errors": errors
                }
            }

        log.info("  [Resonance] AUG Topology is coherent. Phase stabilized.")
        return {
            "status": "stable", 
            "payload": {"topology": topology, "validation": "passed"}
        }