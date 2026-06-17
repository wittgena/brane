# arch.contract.state.node0
## @lineage: topos.contract.state.node0
## @lineage: phase.runtime.state.node0
## @lineage: phase.node.state.node0
"""
@desc: Transient execution context for topological state reset and signal recovery.

This module defines 'node0' not as a physical node, but as a structural zero-point (origin).
It provides a safe context boundary where a PhaseInterpreter can drop its current phase tension,
re-anchor to the base bootstrap domain, and process toxic signals without side effects.
"""
from typing import List, Iterator
from contextlib import contextmanager
import uuid
from arch.proto.event.psi import PsiCarrier
from watcher.plane.emitter import get_emitter
from phase.runtime.interpreter import NodeInterpreter, AnchoredIR, AnchorFlow

log = get_emitter("state.node0")

class Node0State:
    """origin.point for phase cycles: Provides phase reset, recursive reflection, and safe signal reprocessing"""
    def __init__(self, node_id: str):
        self.context_id = f"ctx-0-{uuid.uuid4().hex[:8]}"
        self.node_id = node_id
        ## node0 always holds a pure origin anchor
        self.origin_anchor: AnchoredIR = AnchorFlow.bootstrap()

    def sync_to_origin(self, interpreter: NodeInterpreter) -> NodeInterpreter:
        """
        @action: reset.interpreter
        - Force interpreter to node0 origin
        - Clears dynamic phase prefixes
        - Prepares for recursive spiral reentry
        """
        log.trace(f"[node0:{self.context_id}] Resetting interpreter for {self.node_id}")
        interpreter.anchor = self.origin_anchor
        interpreter.phase = "PHASE_IDLE"
        return interpreter

    def quarantine_collapse_log(self, collapse_log: List[PsiCarrier]) -> List[PsiCarrier]:
        """
        @action: retry.psi / quarantine
        - Sanitize collapse log within node0 topological context
        - Tag toxic signals for quarantine, recoverable signals for re-binding
        - Supports recursive phase reflection
        """
        recovered_signals = []
        for psi in collapse_log:
            ## Example condition: If the signal caused a phase tension/error
            if "error" in psi.kind or "panic" in psi.kind:
                log.trace(f"[node0] Quarantining signal: {psi.symbol}")
                recovered_signals.append(
                    PsiCarrier(
                        source=psi.source,
                        kind=f"{psi.kind}:quarantined",
                        tag=psi.tag
                    )
                )
            else:
                ## Normal unhandled signals are prepped for re-evaluation in the new phase
                log.trace(f"[node0] Prepping signal for retry: {psi.symbol}")
                recovered_signals.append(
                    PsiCarrier(
                        source=psi.source,
                        kind=f"{psi.kind}:retry",
                        tag=psi.tag
                    )
                )
        return recovered_signals

@contextmanager
def enter_node0(interpreter: NodeInterpreter, node_id: str) -> Iterator[Node0State]:
    """
    @contextmanager: enter_node0
    @flow: unbind → reset to 0 → yield safe context → rebind to spiral
    
    @usage:
        with enter_node0(interpreter, "node-123") as n0:
            recovered_log = n0.quarantine_collapse_log(failed_signals)
    """
    log.trace(f"[node0] {node_id} ENTERS origin context")
    n0_state = Node0State(node_id)
    try:
        ## phase.1: Force the interpreter into the origin state
        n0_state.sync_to_origin(interpreter)
        
        ## phase.2: Yield the safe environment to the caller (e.g., dispatcher)
        yield n0_state
    except Exception as e:
        ## Reversible exit: Even if recovery fails, node0 catches it to prevent system halt
        log.trace(f"[node0] Exception caught inside origin context: {e}. Forcing hard reset.")
        n0_state.sync_to_origin(interpreter)
        
    finally:
        ## phase.3: Exit bound - Interpreter is now ready to resume processing new psi flows
        log.trace(f"## [node0] {node_id} EXITS origin context. Ready at {interpreter.phase}")