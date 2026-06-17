# arch.contract.interface
## @lineage: topos.contract.interface
## @lineage: phase.runtime.contract.interface
"""
@phase
- ψ: event signal resonance around
- Φ: shared field state where tension accumulates
- ∂Φ: observers aligning drift and detecting rupture
- Σ: dispersion / aggregation of macro-micro flows

@flow: ψ → ator interaction → Φ drift → ∂Φ detection → rupture → new Φ regime
"""
from __future__ import annotations
from typing import Tuple, List, Dict, Any, Optional
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Dict, Optional, Any, Protocol
from arch.proto.event.psi import PsiEvent

class IPhaseField(ABC):
    """Φ-field: shared phase space where system tension accumulates"""
    @abstractmethod
    def get_state(self) -> Dict[str, float]: pass
    @abstractmethod
    def evolve(self, dt: float) -> None: pass
    @abstractmethod
    def compute_gradient(self) -> Dict[str, float]: pass

class IPhaseAtor(ABC):
    """ψ↔Φ interface node"""
    @property
    @abstractmethod
    def ator_id(self) -> str: pass
    @property
    @abstractmethod
    def state(self) -> Dict[str, Any]: pass
    @abstractmethod
    def set_state(self, new_state: str) -> None: pass # 캡슐화 메서드 추가
    @abstractmethod
    async def react(self, event: PsiEvent, field: IPhaseField, bus: IEventBus) -> None:
        """Ator processes incoming ψ under current Φ conditions and emits derived ψ via the event bus"""
        pass

class IEventBus(ABC):
    """
    ψ-router: asynchronous transport layer for phase events.

    Responsibilities:
    - publish ψ into the system stream
    - route ψ to ators based on topology predicates
    """

    @abstractmethod
    async def publish(self, event: PsiEvent) -> None:
        pass

    @abstractmethod
    def subscribe(ator: IPhaseAtor, predicate: Callable) -> None:
        pass

class ICriticalDetector(ABC):
    """∂Φ observer: monitors drift within the phase field"""
    @abstractmethod
    def extract(self, field: IPhaseField) -> Dict[str, float]: pass
    @abstractmethod
    def evaluate(self, field: IPhaseField, history: List[PsiEvent], current_tick: int) -> Optional[PsiEvent]: pass

class ISystemRegime(ABC):
    """
    Φ-regime: post-rupture attrator that redefines system constraints.

    A regime modifies:
    - field dynamics (Φ)
    - ator behavior
    - event resonance rules
    """
    @abstractmethod
    def modify_field(self, field: IPhaseField) -> None:
        pass

    @abstractmethod
    def constrain_ator(self, ator: IPhaseAtor) -> None:
        pass

    @abstractmethod
    def filter_event(self, event: PsiEvent) -> Optional[PsiEvent]:
        pass

class IDynamicsKernel(Protocol):
    def compute_step(self, states: Dict[str, Dict[str, Any]], dt: float) -> Dict[str, Dict[str, float]]:
        """현재 상태(states)를 받아, dt 시간 동안 변화할 델타값(d_phase, d_tension 등)을 반환"""
    def render_state(self, states: Dict[str, Dict[str, Any]]) -> str:
        pass

class IBoundExecutor(ABC):
    """@phase.bound: ∂Φ → ∂Φ′"""

    @abstractmethod
    async def execute(self, field: IPhaseField) -> bool:
        """returns: bool → boundary success / failure"""
        pass