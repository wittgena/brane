# bound.router.manager.gateway
## @lineage: bound.channel.manager.gateway
## @lineage: channel.manager
"""
- Design by Contract: All traffic must adhere to explicit Promises.
- State Transition: Contexts are strictly immutable. Routing dictates state derivation.
- Type Promotion: No gateway entry is permitted without Tribunal type-promotion (VettedContext[P, V]).
"""
import asyncio
from enum import Enum, auto
from typing import Any, Annotated, TypeVar, Generic, Optional
from dataclasses import dataclass
from typing_extensions import Protocol
from arch.contract.exp.promise import future

class CauseType(Enum):
    PRE_CONDITION_VIOLATED = auto()
    POST_CONDITION_VIOLATED = auto()
    RESOURCE_EXHAUSTED = auto()
    EXTERNAL_RUPTURE = auto()

@dataclass(frozen=True)
class Cause:
    type: CauseType
    detail: Any

    def is_fallback_eligible(self) -> bool:
        """@model.rule: Contract violations are strictly forbidden from fallback."""
        return self.type in {CauseType.RESOURCE_EXHAUSTED, CauseType.EXTERNAL_RUPTURE}

class NotYetCrystallized(Exception):
    """@model.suspension: Intentional halt triggered by future spaces. Not a standard Failure."""
    pass

class Promise(Protocol):
    contract: str
    invariant: str
    consequence: str

class StreamablePromise(Promise, Protocol):
    """@promise.action: DriverGateway exclusive. Only requires pre-flight."""
    pass

class AuditablePromise(Promise, Protocol):
    """@promise.harvest: LMGateway exclusive. Requires post-execution audit."""
    pass

class SurvivalPromise(Promise, Protocol):
    """@promise.fallback: LocalGateway exclusive. Bound to local resource limits."""
    pass

P = TypeVar('P', bound=Promise)

@dataclass(frozen=True)
class Verdict(Generic[P]):
    promise_id: str
    is_approved: bool
    cause: Optional[Cause] = None
    ## @question: Should 'chain' (provenance history) be maintained as a linked list here, 
    ## or is tracking just the last Verdict sufficient for the type contract?
    # chain: Optional['Verdict'] = None 

@dataclass(frozen=True)
class RawContext:
    """@type.state: Immutable raw request. Gateway entry is strictly forbidden."""
    payload: dict
    is_fallback_derived: bool = False

V = TypeVar('V', bound=Verdict)

@dataclass(frozen=True)
class VettedContext(Generic[P, V]):
    """
    @type.state: Promoted context. 
    The type signature [P, V] statically guarantees which promise it passed.
    """
    raw: RawContext
    verdict: V

StreamResponse = Annotated[Any, "Asynchronous iterator containing Delta chunks"]

## ---------------------------------------------------------------------------
## 4. Tribunal (Global Policy Engine)
## ---------------------------------------------------------------------------
class GlobalPolicyEngine:
    """
    Implements the Tribunal protocol. 
    Holds the exclusive authority to promote RawContext to VettedContext.
    """
    
    @future("Awaiting implementation of judicial and financial quantification logic.")
    def judge(self, candidate: RawContext, promise: P) -> Verdict[P]:
        """@model.enforcement: Centralized point for all PreCondition validations."""
        pass

    @future("Awaiting post-audit logic. How should AuditablePromise coordinate multiple constraints?")
    def audit_trajectory(self, context: VettedContext[AuditablePromise, Any], response: Any, promise: AuditablePromise) -> None:
        """
        @contract.audit: Only defined for AuditablePromise. 
        Asymmetry justified by the type signature.
        """
        pass

class DriverGateway:
    async def stream_forward(self, ctx: VettedContext[StreamablePromise, Any]) -> StreamResponse:
        """@contract.boundary: Accepts ONLY contexts that passed StreamablePromise."""
        pass

class LMGateway:
    async def forward(self, ctx: VettedContext[AuditablePromise, Any]) -> Any:
        """@contract.boundary: Accepts ONLY contexts that passed AuditablePromise."""
        pass

class LocalGateway:
    @future("Awaiting integration with local VRAM router.")
    async def direct_call(self, ctx: VettedContext[SurvivalPromise, Any]) -> Any:
        """@contract.boundary: Accepts ONLY contexts that passed SurvivalPromise."""
        pass

class GatewayManager:
    def __init__(self, policy_engine: GlobalPolicyEngine):
        self.policy_engine = policy_engine
        self.driver_gw = DriverGateway()
        self.lm_gw = LMGateway()
        self.local_gw = LocalGateway()

        ## @future: Instances of concrete promises to be injected or instantiated here
        self.action_promise: StreamablePromise = ... # type: ignore
        self.harvest_promise: AuditablePromise = ... # type: ignore
        self.fallback_promise: SurvivalPromise = ... # type: ignore

    async def execute(self, ctx: RawContext) -> Any:
        """The unified Facade. Routes traffic by deriving states, not mutating them."""
        target_promise = self._dispatch(ctx)
        
        try:
            verdict = self.policy_engine.judge(ctx, target_promise)
            
            if not verdict.is_approved:
                ## @flow.halt: Pre-flight failure. Do not attempt fallback for contract violations.
                raise Exception(f"Tribunal Rejection: {verdict.cause}")

            vetted_ctx = VettedContext(raw=ctx, verdict=verdict)

            if isinstance(target_promise, StreamablePromise):
                return await self.driver_gw.stream_forward(vetted_ctx) # type: ignore
            
            elif isinstance(target_promise, AuditablePromise):
                response = await self.lm_gw.forward(vetted_ctx) # type: ignore
                self.policy_engine.audit_trajectory(vetted_ctx, response, target_promise)
                return response
                
            elif isinstance(target_promise, SurvivalPromise):
                return await self.local_gw.direct_call(vetted_ctx) # type: ignore

        except NotYetCrystallized as e:
            ## @flow.rupture: Intentional suspension.
            raise e
        except Exception as e:
            ## @question: Currently catching all Exceptions from Gateways to trigger fallback.
            ## Should Gateways throw specific `Cause` ADTs to map cleanly to `fallback_eligible`?
            cause = Cause(type=CauseType.EXTERNAL_RUPTURE, detail=str(e))
            
            if cause.is_fallback_eligible() and not ctx.is_fallback_derived:
                ## @flow.transition: Generate a completely new context, preserving the original payload.
                fallback_ctx = RawContext(payload=ctx.payload, is_fallback_derived=True)
                return await self.execute(fallback_ctx)
            raise e

    def _dispatch(self, ctx: RawContext) -> Promise:
        """@flow.routing: Routing is purely functional based on immutable state"""
        if ctx.is_fallback_derived:
            return self.fallback_promise
        elif ctx.payload.get("is_batch_or_eval"):
            return self.harvest_promise
        
        return self.action_promise