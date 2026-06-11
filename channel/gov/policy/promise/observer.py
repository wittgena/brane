# channel.gov.policy.promise.observer
## @lineage: gov.gateway.policy.promise.observer
## @lineage: gov.gateway.promise.observer
from __future__ import annotations
import time
from decimal import Decimal
from typing import List, Optional, Dict, Any
from arch.contract.exp.promise import future, Promise
from pydantic import BaseModel
from channel.gov.policy.budget import Psi, Residue, TokenContext, TokenVerdict
from channel.gov.policy.iam import SystemicRisk, PolicyVerdict
from channel.gov.policy.resonance import TopologicalContext, ResonanceVerdict
from watcher.plane.emitter import get_emitter

log = get_emitter("promise.observer")

class PromiseObserver:
    """IAM(보안), Token(재무), Topology(진화) 이벤트를 모두 수집하는 중앙 관측소"""
    def __init__(self):
        self.shift_history: List[Dict[str, Any]] = []
        self.rupture_history: List[Residue] = []
        self.security_blocks: List[Dict[str, Any]] = []  
        self.resonance_logs: List[Dict[str, Any]] = [] # [추가] 공명/동화 기록
        self.state_observations: List[TokenContext] = [] 

    @future("Stream TokenContext via Kafka/gRPC to ClickHouse for real-time drift detection.")
    def observe_state(self, ctx: TokenContext) -> None:
        self.state_observations.append(ctx)

    def record_shift(self, ctx: TokenContext, verdict: TokenVerdict) -> None:
        self.shift_history.append({"ts": time.time(), "decision": verdict.decision.value, "rationale": verdict.rationale})

    @future("Background DSPy optimizer fetches Ruptures to compile cheaper counterfactual prompts.")
    def record_rupture(self, residue: Residue) -> None:
        self.rupture_history.append(residue)

    def record_security_block(self, risk: SystemicRisk, verdict: PolicyVerdict) -> None:
        log.warning(f"[Security Block] Source: {risk.source} | Rationale: {verdict.rationale}")
        self.security_blocks.append({"ts": time.time(), "risk": risk.model_dump(), "verdict": verdict.model_dump()})
        
    def record_resonance(self, ctx: TopologicalContext, verdict: ResonanceVerdict) -> None:
        self.resonance_logs.append({"ts": time.time(), "topology": ctx.model_dump(), "verdict": verdict.model_dump()})