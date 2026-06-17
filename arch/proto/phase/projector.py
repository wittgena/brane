# arch.proto.phase.projector
## @lineage: arch.proto.projector
from abc import ABC, abstractmethod
from typing import Generic, TypeVar, List, Any, Optional
from watcher.plane.emitter import get_emitter

log = get_emitter("proto.projector")

## @archetype
T_Node = TypeVar('T_Node')       ## Φ: topology node (observed unit)
T_Context = TypeVar('T_Context') ## Ψ_ctx: The lens / perspective (focus, depth, relations)
T_Rep = TypeVar('T_Rep')         ## R: projected representation
T_Surface = TypeVar('T_Surface') ## Φs: assembled surface structure

class PhaseProjector(ABC, Generic[T_Node, T_Context, T_Rep, T_Surface]):
    """
    Abstract pipeline projecting topology (Φ) into a contextual surface structure (Φs).
    """
    
    def compile(self, context: Optional[T_Context] = None) -> T_Surface:
        """
        Executes the contextual projection pipeline: 
        Scan → Select (Context) → Project → Assemble → Emit
        """
        log.info("[AUG] Contextual Surface Compile Initiated")
        
        # 1. Input Graph (Base Topology)
        topology: List[T_Node] = self.scan()
        log.info(f"## @scan: {len(topology)} absolute items found in Φ.")
        
        # 2. Contextual Selection (Slicing Φ → Ψ)
        subgraph: List[T_Node] = self.select(topology, context)
        log.info(f"## @select (Contextualized): {len(subgraph)} items sliced via lens.")
        
        # 3. Structural Projection (Ψ → R)
        representations: List[T_Rep] = self.project(subgraph, context)
        log.info(f"## @extract (Projected): {len(representations)} items structurally mapped.")
        
        # 4. Surface Assembly (R → Φs)
        surface: T_Surface = self.assemble(representations, context)
        log.info("## @group (Assembled): Surface topology aligned.")
        
        # 5. Materialization
        self.emit(surface, context)
        log.info("## @emit: Contextual Surface projection completed.")
        log.info("[UGA] compile completed")
        
        return surface

    @abstractmethod
    def scan(self) -> List[T_Node]:
        """
        @phase: Base Observation
        @action: Collect the entire topology nodes (Φ) from the source.
        """
        pass

    @abstractmethod
    def select(self, topology: List[T_Node], context: Optional[T_Context]) -> List[T_Node]:
        """
        @phase: Contextual Slicing (Replaces static filter)
        @action: Extract a dynamic subgraph (Ψ) based on the given context constraints.
        """
        pass

    @abstractmethod
    def project(self, subgraph: List[T_Node], context: Optional[T_Context]) -> List[T_Rep]:
        """
        @phase: Representation Translation
        @action: Map the sliced nodes into format-specific representations (R).
        """
        pass

    @abstractmethod
    def assemble(self, representations: List[T_Rep], context: Optional[T_Context]) -> T_Surface:
        """
        @phase: Structural Assembly
        @action: Group and align representations into the final surface blueprint (Φs).
        """
        pass

    @abstractmethod
    def emit(self, surface: T_Surface, context: Optional[T_Context]) -> None:
        """
        @phase: Materialization
        @action: Render or write the assembled surface (e.g., Markdown, JSON).
        """
        pass