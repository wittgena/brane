# watcher.ator.regime
## @lineage: surface.ator.regime
## @lineage: xyz.surface.ator.regime
## @lineage: xyz.subst.ator.regime
## @lineage: foldbox.manager.workspace.regime
import math
import random
from typing import Optional
from arch.contract.registry.unified import contract
from arch.contract.interface import ISystemRegime, IPhaseField, IPhaseAtor
from arch.proto.event.psi import PsiEvent

@contract.regime("node.regime")
class NodeRegime(ISystemRegime):
    """
    @role: Γ_rupture actuator | System reset & topological realignment
    @flow: XeCont → Φ.commit() → Γ.modify_field()
    """
    def __init__(self, **kwargs):
        self.params = kwargs

    def modify_field(self, field: IPhaseField) -> None:
        """
        @phase.execution: Topology Reset
        - @step.1: tension(all) → 0.0
        - @step.2: phase(NORMAL) → random(0, 2π) [Scattering]
        - @step.3: phase(REFLECTOR) → 0.0 [New Baseline]
        - @step.4: pressure(Φ) → 0.0 [Absolute Vacuum]
        """
        states = field.get_state()
        
        for node_id, data in states.items():
            ## @trace: release condensed fatigue
            data["tension"] = 0.0
            
            if data["state"] == "NORMAL":
                data["phase"] = random.uniform(0, 2 * math.pi)
            elif data["state"] == "REFLECTOR":
                data["phase"] = 0.0  

        if hasattr(field, 'pressure'):
            field.pressure = 0.0
            
        print("[Regime] Field collapsed and reformed. Tension reset to 0.0")

    def constrain_ator(self, ator: IPhaseAtor) -> None:
        ## @flow: Γ → constraint(Ator)
        pass

    def filter_event(self, event: PsiEvent) -> Optional[PsiEvent]:
        """
        @invariant: Ψ_event.epoch == "new"
        @step: Drop residues from prior epochs (Ψ_old → ∅)
        """
        if event.context.get("epoch") != "new":
            pass
        return event