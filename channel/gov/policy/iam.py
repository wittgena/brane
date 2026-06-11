# channel.gov.policy.iam
## @lineage: gov.gateway.policy.iam
from __future__ import annotations
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field, ConfigDict
from typing import Annotated
from arch.contract.exp.promise import future, Promise
from watcher.plane.emitter import get_emitter

log = get_emitter("policy.iam")

safety_promise = Promise(
    contract="에이전트는 CRITICAL 등급의 행위를 단독으로 실행할 수 없다.",
    invariant="SystemicRisk.severity < CRITICAL or Directive != PROCEED",
    consequence="시스템 인프라 파괴 및 무단 데이터 유출",
)

class RiskSeverity(int, Enum):
    UNKNOWN = 0
    TRIVIAL = 10       
    MODERATE = 50      
    CRITICAL = 100     

class SystemicRisk(BaseModel):
    """(System) 토큰 정책의 TokenContext에 대응하는 리스크 벡터"""
    model_config = ConfigDict(frozen=True)
    severity: RiskSeverity = RiskSeverity.UNKNOWN
    source: str  
    signatures: List[str] = Field(default_factory=list)  
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def is_riskier_than(self, threshold: RiskSeverity) -> bool:
        return self.severity >= threshold

class ActionDirective(str, Enum):
    PROCEED = "proceed"                 
    QUARANTINE = "quarantine"           
    REQUIRE_PROOF = "require_proof"     

class PolicyVerdict(BaseModel):
    """(System) 토큰 정책의 TokenVerdict에 대응하는 판결문"""
    directive: ActionDirective
    rationale: str
    required_proof_schema: Optional[str] = None  
    metadata: Dict[str, Any] = Field(default_factory=dict)

class GovernancePolicy(BaseModel, ABC):
    """Nexus 거버넌스 정책의 추상 기저 클래스"""
    model_config = ConfigDict(extra="forbid")
    kind: str  

    @abstractmethod
    def evaluate(self, risk: SystemicRisk) -> PolicyVerdict:
        pass

class BlockCriticalPolicy(GovernancePolicy):
    kind: Literal["BlockCriticalPolicy"] = "BlockCriticalPolicy"
    
    def evaluate(self, risk: SystemicRisk) -> PolicyVerdict:
        if risk.is_riskier_than(RiskSeverity.CRITICAL):
            return PolicyVerdict(
                directive=ActionDirective.QUARANTINE,
                rationale=f"Risk severity {risk.severity.name} exceeds CRITICAL threshold."
            )
        return PolicyVerdict(
            directive=ActionDirective.PROCEED,
            rationale="Risk is below CRITICAL threshold."
        )

class ConsensusRequiredPolicy(GovernancePolicy):
    kind: Literal["ConsensusRequiredPolicy"] = "ConsensusRequiredPolicy"
    threshold: RiskSeverity = RiskSeverity.MODERATE
    require_on_unknown: bool = True

    def evaluate(self, risk: SystemicRisk) -> PolicyVerdict:
        if risk.severity == RiskSeverity.UNKNOWN and self.require_on_unknown:
            return PolicyVerdict(
                directive=ActionDirective.REQUIRE_PROOF,
                rationale="Unknown risk vectors require explicit justification.",
                required_proof_schema="Counterfactual_Rationale"
            )
        if risk.is_riskier_than(self.threshold):
            return PolicyVerdict(
                directive=ActionDirective.REQUIRE_PROOF,
                rationale=f"Risk {risk.severity.name} requires proof of alignment.",
                required_proof_schema="ROI_Calculation_Or_Safety_Guarantee"
            )
        return PolicyVerdict(
            directive=ActionDirective.PROCEED,
            rationale="Risk is acceptable without proof."
        )

## Polymorphic Router
AnySystemPolicy = Annotated[
    Union[BlockCriticalPolicy, ConsensusRequiredPolicy],
    Field(discriminator="kind")
]