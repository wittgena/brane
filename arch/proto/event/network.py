# arch.proto.event.network
## @lineage: phase.bind.event.network
from abc import ABC, abstractmethod
from typing import Generic, TypeVar, List, Dict, Any, Optional
from watcher.plane.emitter import get_emitter

log = get_emitter("event.network")

Psi = TypeVar('Psi')           ## psi: dynamic flow (task / message)
Phi = TypeVar('Phi')           ## phi: shared topology (state / memory)
R = TypeVar('R')               
EventId = TypeVar('EventId')   ## psi identifier

class EventDisperser(ABC, Generic[Psi, R, Phi]):
    """@flow: ψ -> {ψ₁..ψₙ} -> {R₁..Rₙ} -> Φ_merged"""

    @abstractmethod
    def scatter(self, task: Psi) -> List[Psi]:
        """Split a task into parallel subflows."""
        pass

    @abstractmethod
    def gather(self, representations: List[R]) -> Phi:
        """Merge parallel representations into a unified state."""
        pass

class EventRouter(ABC, Generic[Psi, Phi, EventId]):
    """@flow: ψ_in → Φ_rules → ψ_out_k"""

    def __init__(self, rules_topology: Phi):
        self.rules = rules_topology  # routing decision topology

    @abstractmethod
    def dispatch(self, task: Psi) -> EventId:
        """Select the target ator based on routing rules."""
        pass

class EventAligner(ABC, Generic[Psi, Phi]):
    """@flow: ψ → ∂Φ → Φ′ → Φ"""

    @abstractmethod
    def detect_drift(self, event: Psi, current_state: Phi) -> Phi:
        """Detect state drift caused by an event."""
        pass

    @abstractmethod
    def reconcile(self, drift_analysis: Phi, current_state: Phi) -> Phi:
        """Reconcile drift and synchronize shared state."""
        pass

class EventResonator(ABC, Generic[Psi]):
    """@flow: ψ → interference → resonance → ψ_amplified"""

    @abstractmethod
    def interfere(self, flow_a: Psi, flow_b: Psi) -> Psi:
        """Create interference between two flows (e.g. generator vs critic)."""
        pass

    @abstractmethod
    def amplify(self, interference_result: Psi, iterations: int) -> Psi:
        """Iteratively refine and amplify the result."""
        pass

class EventTransductor(ABC, Generic[Psi]):
    """@flow: ψ₁ → transductor → ψ₂"""

    @abstractmethod
    def transduce(self, source_flow: Psi, target_format_rule: Any) -> Psi:
        """Convert flow representation for another ator (e.g. NL → JSON)."""
        pass

class MultiEventFlow(ABC, Generic[Psi, Phi]):
    """Hybrid control loop combining the five primitives."""

    def __init__(self):
        self.shared_state: Optional[Phi] = None

    @abstractmethod
    def execute_flow(self, initial_flow: Psi) -> Phi:
        """
        @flow: ψ → dispersion → routing → transduction → alignment → resonance → Φ
        - Execute the full multi-ator flow cycle.
        """
        pass
