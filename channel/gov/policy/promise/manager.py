# channel.gov.policy.promise.manager
## @lineage: gov.gateway.policy.promise.manager
## @lineage: gov.gateway.check.promise
from __future__ import annotations
import time
from decimal import Decimal
from typing import List, Optional, Dict, Any
from arch.contract.exp.promise import future, Promise
from pydantic import BaseModel
from channel.gov.policy.budget import Psi, Residue, ShiftDecision, TokenContext, TokenVerdict, AnyTokenPolicy
from channel.gov.policy.iam import SystemicRisk, ActionDirective, PolicyVerdict, AnySystemPolicy, RiskSeverity
from channel.gov.policy.resonance import TopologicalContext, ResonanceVerdict, ResonanceDirective, AnyResonancePolicy
from channel.gov.policy.promise.observer import PromiseObserver
from watcher.plane.emitter import get_emitter

log = get_emitter("check.promise")

elasticity_promise = Promise(
    contract="에이전트의 토큰 소모는 max_elasticity를 초과할 수 없다.",
    invariant="current_tension <= max_elasticity",
    consequence="연쇄적 Rate Limit 도달 및 API 과금 폭탄",
)

## Integrated Nexus Manager (The Gateway)
class AgentAction(BaseModel):
    """에이전트가 시스템에 가하려는 행동의 총체적 메타데이터 (3대 차원 포함)"""
    risk: SystemicRisk             # 제1차원: 보안
    topology: TopologicalContext   # 제2차원: 진화/위상 [추가됨]
    psi: Psi                       # 제3차원: 에너지/대사

class PromiseManager:
    """3대 정책(IAM, Resonance, Budget)을 직렬 파이프라인으로 연결하는 최상위 게이트웨이"""
    def __init__(
        self, 
        name: str, 
        base_threshold: Decimal, 
        max_elasticity: Decimal,
        iam_policy: AnySystemPolicy,           # 1차 관문: 면역
        resonance_policy: AnyResonancePolicy,  # 2차 관문: 공명 [추가됨]
        budget_policy: AnyTokenPolicy,         # 3차 관문: 대사
        governance: PromiseObserver
    ):
        self.name = name
        self.base_threshold = base_threshold
        self.current_threshold = base_threshold
        self.max_elasticity = max_elasticity   
        self.current_tension = Decimal("0")    
        
        self.iam_policy = iam_policy
        self.resonance_policy = resonance_policy
        self.budget_policy = budget_policy
        self.governance = governance

    def execute(self, action: AgentAction) -> Optional[Residue]:
        """행동 실행의 진입점: 면역(IAM) -> 기억(Resonance) -> 대사(Budget) 순으로 진행"""
        log.info(f"\n[{self.name}] ⚡ 행동 요청 접수: '{action.psi.name}'")

        # ==========================================
        # Gate 1: IAM Policy (면역학적 검열)
        # ==========================================
        iam_verdict = self.iam_policy.evaluate(action.risk)
        
        if iam_verdict.directive == ActionDirective.QUARANTINE:
            self.governance.record_security_block(action.risk, iam_verdict)
            return self._collapse(action.psi, f"Immune Rejection: {iam_verdict.rationale}")

        if iam_verdict.directive == ActionDirective.REQUIRE_PROOF:
            return self._invoke_tribunal_verification(action, iam_verdict)

        log.info(" └─ [Gate 1 통과] 면역 반응 없음 (PROCEED)")

        # ==========================================
        # Gate 2: Resonance Policy (진화적 기억 공명)
        # ==========================================
        res_verdict = self.resonance_policy.evaluate(action.topology)
        self.governance.record_resonance(action.topology, res_verdict)
        
        if res_verdict.directive == ResonanceDirective.ASSIMILATE:
            # [아키텍처의 백미] 과거의 성공적 위상과 완벽히 공명하면, 대사(Budget) 과정을 바이패스합니다.
            log.info(f" └─ [Gate 2 공명] 완벽한 레퍼런스 발현({res_verdict.reference_id}). 대사 에너지 소모 생략 (ASSIMILATE)")
            return None # 성공적으로 흡수됨 (찌꺼기 없음)
            
        elif res_verdict.directive == ResonanceDirective.MUTATE:
            log.info(f" └─ [Gate 2 변이] 유사 레퍼런스 발현({res_verdict.reference_id}). 변이 후 대사 검증으로 진행 (MUTATE)")
            # 필요하다면 여기서 action.psi.amount(예상 토큰 소모량)를 깎아주는 할인을 적용할 수도 있습니다.
            
        elif res_verdict.directive == ResonanceDirective.PIONEER:
            log.info(" └─ [Gate 2 개척] 미지의 위상. 신규 개척을 위해 대사 검증으로 진행 (PIONEER)")

        # ==========================================
        # Gate 3: Budget Policy (열역학적 대사 통제)
        # ==========================================
        prospective_tension = self.current_tension + action.psi.amount
        
        if prospective_tension > self.max_elasticity:
            return self._collapse(action.psi, "Violated: elasticity_promise (Metabolic Rupture)")

        ctx = TokenContext(
            current_tension=prospective_tension,
            current_threshold=self.current_threshold,
            max_elasticity=self.max_elasticity,
            psi=action.psi,
            history_summary=self._summarize_history()
        )
        self.governance.observe_state(ctx) 
        budget_verdict = self.budget_policy.evaluate(ctx)  

        return self._apply_budget(budget_verdict, ctx, action.psi)

    def _apply_budget(self, verdict: TokenVerdict, ctx: TokenContext, psi: Psi) -> Optional[Residue]:
        if verdict.decision == ShiftDecision.ABSORB:
            self.current_tension += psi.amount
            log.info(f" └─ [Gate 3 승인] ABSORB. 누적 텐션={self.current_tension} IC")
            return None

        if verdict.decision in (ShiftDecision.EXPAND_SOFT, ShiftDecision.EXPAND_HARD):
            self.current_threshold = verdict.new_threshold
            self.current_tension += psi.amount
            self.governance.record_shift(ctx, verdict)
            log.info(f" └─ [Gate 3 승인] EXPAND. 누적 텐션={self.current_tension} IC")
            return None

        if verdict.decision == ShiftDecision.STEP_UP_VERIFY:
            return self._invoke_tribunal_verification(AgentAction(risk=SystemicRisk(source="budget"), topology=TopologicalContext(schema_hash="null", domain_tags=[], complexity=0), psi=psi), None)

        return self._collapse(psi, verdict.rationale)

    @future("Zero-Knowledge & Consensus Tribunal...")
    def _invoke_tribunal_verification(self, action: AgentAction, iam_verdict: Optional[PolicyVerdict]) -> Optional[Residue]:
        return self._collapse(action.psi, "Tribunal Consensus Not Yet Crystallized")

    def _collapse(self, psi: Psi, reason: str) -> Residue:
        residue = Residue(source_bound=self.name, requested_tokens=psi.amount, declined_amount=psi.amount, reason=reason)
        self.governance.record_rupture(residue)
        return residue

    def _summarize_history(self) -> Dict[str, Any]:
        return {
            "recent_shifts": len(self.governance.shift_history),
            "recent_ruptures": len(self.governance.rupture_history),
            "recent_security_blocks": len(self.governance.security_blocks),
            "recent_resonances": len(self.governance.resonance_logs) # [추가]
        }