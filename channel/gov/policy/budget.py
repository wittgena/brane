# channel.gov.policy.budget
## @lineage: gov.gateway.policy.budget
from __future__ import annotations
import time
from abc import ABC, abstractmethod
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field, ConfigDict
from typing import Annotated
from arch.contract.exp.promise import future, Promise, NotYetCrystallized
from watcher.plane.emitter import get_emitter

log = get_emitter("policy.budget")

elasticity_promise = Promise(
    contract="에이전트의 토큰 소모는 max_elasticity를 초과할 수 없다.",
    invariant="current_tension <= max_elasticity",
    consequence="연쇄적 Rate Limit 도달 및 API 과금 폭탄",
)

class Psi(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    amount: Decimal
    context: Dict[str, Any] = Field(default_factory=dict)

class Residue(BaseModel):
    model_config = ConfigDict(frozen=True)
    source_bound: str
    requested_tokens: Decimal
    declined_amount: Decimal
    reason: str
    timestamp: float = Field(default_factory=time.time)

class ShiftDecision(str, Enum):
    ABSORB = "absorb"
    EXPAND_SOFT = "expand_soft"
    EXPAND_HARD = "expand_hard"
    STEP_UP_VERIFY = "step_up"
    DENY = "deny"

class TokenContext(BaseModel):
    """(Token) 시스템 정책의 SystemicRisk에 대응하는 상태 벡터"""
    current_tension: Decimal
    current_threshold: Decimal
    max_elasticity: Decimal
    psi: Psi
    history_summary: Dict[str, Any] = Field(default_factory=dict)

class TokenVerdict(BaseModel):
    """(Token) 시스템 정책의 PolicyVerdict에 대응하는 판결문"""
    decision: ShiftDecision
    new_threshold: Decimal
    confidence: float
    rationale: str  # Dict에서 str로 변경하여 판결문 스타일 통일
    metadata: Dict[str, Any] = Field(default_factory=dict)

class TokenPolicy(BaseModel, ABC):
    """Nexus 토큰 정책의 추상 기저 클래스"""
    model_config = ConfigDict(extra="forbid")
    kind: str  

    @abstractmethod
    def evaluate(self, ctx: TokenContext) -> TokenVerdict:
        pass

class RuleBasedTokenPolicy(TokenPolicy):
    kind: Literal["RuleBasedTokenPolicy"] = "RuleBasedTokenPolicy"

    def evaluate(self, ctx: TokenContext) -> TokenVerdict:
        if ctx.current_tension <= ctx.current_threshold:
            return TokenVerdict(
                decision=ShiftDecision.ABSORB, 
                new_threshold=ctx.current_threshold, 
                confidence=1.0, 
                rationale="Within base budget."
            )
        if ctx.current_tension <= ctx.max_elasticity and ctx.psi.context.get("is_critical", False):
            return TokenVerdict(
                decision=ShiftDecision.EXPAND_SOFT, 
                new_threshold=ctx.current_tension, 
                confidence=0.8, 
                rationale="Critical task triggered soft expansion.",
                metadata={"expansion_amount": float(ctx.current_tension - ctx.current_threshold)}
            )
        return TokenVerdict(
            decision=ShiftDecision.DENY, 
            new_threshold=ctx.current_threshold, 
            confidence=1.0, 
            rationale="Exceeds max elasticity promise."
        )

class PredictiveRoutingPolicy(TokenPolicy):
    kind: Literal["PredictiveRoutingPolicy"] = "PredictiveRoutingPolicy"

    @future("Cost-Aware Speculative Routing via Reward Model.")
    def evaluate(self, ctx: TokenContext) -> TokenVerdict:
        raise NotYetCrystallized("지능형 라우팅 모델은 아직 컴파일되지 않았습니다.")

## Polymorphic Router
AnyTokenPolicy = Annotated[
    Union[RuleBasedTokenPolicy, PredictiveRoutingPolicy],
    Field(discriminator="kind")
]