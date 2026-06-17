# arch.contract.protocol
## @lineage: topos.contract.protocol
## @lineage: phase.runtime.contract.protocol
"""@desc: Proto decorator (non-executing structural record)"""
from typing import Tuple, Any, Callable, Union, Type, TypeVar
from dataclasses import dataclass

PhaseElement = Union[str, Type[Any]]

@dataclass(frozen=True)
class Proto:
    sequence: Tuple[PhaseElement, ...]
    kind: str = "phase"

def proto(p: Proto) -> Callable:
    """
    @invariant:
    - execution != proto
    """
    def wrap(obj: Any) -> Any:
        setattr(obj, "__proto__", p)
        return obj
    return wrap

@proto(Proto(
    sequence=("Φ", "kernel", "ΔΦ", "Φ"),
    kind="evolution"
))
def evolve(self, dt: float):
    pass

def get_proto(obj: Any) -> Proto:
    return getattr(obj, "__proto__", None)

T = TypeVar('T')

def extend_proto(p: Proto, *seq: str, kind: str = None) -> Proto:
    """기존 Proto를 변형하지 않고 확장된 새로운 Proto를 반환 (순수 함수)"""
    return Proto(
        sequence=p.sequence + seq,
        kind=kind or p.kind
    )

BASE_LOOP = Proto(("Ψ", "Φ′", "Φ", "Ψ′"), "loop")

@proto(BASE_LOOP)
async def interpret(self):
    pass
