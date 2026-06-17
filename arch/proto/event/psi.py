# arch.proto.event.psi
## @lineage: phase.bind.event.psi
## @lineage: arch.event.psi
## @lineage: arch.contract.event.psi
## @lineage: arch.model.event.psi
## @lineage: topos.contract.event.psi
## @lineage: phase.runtime.contract.event.psi
"""
@flow:
Ψ (carrier)
 → ∂Φ (domain boundary resolve)
 → Φ′ (phase transition evaluation)
 → {θ resonance | θ interference}
 → δ (optional structural anchoring)
 → Φ⁺ (anchored structure)
"""
import __future__
import time
import json
from enum import Enum
from typing import Dict, Tuple, FrozenSet, Optional, Any, Union
from dataclasses import dataclass, field, asdict
from arch.proto.event.next import LogEvent
from watcher.plane.emitter import get_emitter

log = get_emitter("bridge.psi")

## resonance (Ψ behavior)
class CarrierType(str, Enum):
    """resonance (Ψ behavior)"""
    RECURSIVE = "recursive"      # self-referential resonance
    MODULATORY = "modulatory"    # indirect / delayed resonance
    FIXED = "fixed"              # constrained / invariant resonance
    DIFFUSE = "diffuse"          # distributed resonance

## Φ Field
class PhaseField(str, Enum):
    LOCAL = "local"
    COHERENT = "coherent"
    INTERFERENCE = "interference"
    EVALUATION = "evaluation"

## Ψ Carrier
@dataclass(frozen=True)
class PsiCarrier:
    kind: str
    tag: str
    payload: Any
    carrier_type: Optional[CarrierType] = CarrierType.FIXED
    target_field: Optional[PhaseField] = PhaseField.LOCAL

    @property
    def symbol(self) -> str:
        """boundary routing symbol (∂Φ input)"""
        return f"{self.kind}:{self.tag}"

@dataclass
class PsiEvent:
    """minimal unit of phase resonance"""
    event_id: str  
    parent_id: Optional[str]
    source_id: str
    scope: str
    tick: int
    
    carrier: PsiCarrier
    phase_id: int = 0
    context: Dict[str, Any] = field(default_factory=dict)

    @property
    def payload(self) -> str:
        """기존 시스템과의 호환성을 위해 property로 제공"""
        return self.carrier.payload

    @property
    def event_type(self) -> str:
        """기존 시스템과의 호환성을 위해 property로 제공"""
        return self.carrier.kind
        
    @property
    def symbol(self) -> str:
        """라우팅 심볼 위임"""
        return self.carrier.symbol

    # @property
    # def target_field(self):
    #     """계층을 건너뛰는 접근을 위한 위상 브릿지"""
    #     return self.carrier.target_field if self.carrier else None

    @property
    def tag(self) -> str:
        """tag 위임"""
        return self.carrier.tag

    @property
    def kind(self) -> str:
        """kind 위임"""
        return self.carrier.kind
    
    def to_json(self) -> str:
        """객체를 JSON 문자열로 변환 (Surface 투영용)"""
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, json_str: str):
        """JSON 문자열을 객체로 복원 (Capture용)"""
        data = json.loads(json_str)
        return cls(**data)

PsiType = Union[PsiCarrier, PsiEvent]
