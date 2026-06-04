# bound.exam.flow
## @lineage: hub.flow
## @lineage: gov.consensus.flow
## @lineage: meta.judgment.flow
## @lineage: meta.flow.judgment
import time
import random
from typing import Dict, Any
from watcher.plane.emitter import get_emitter
from arch.contract.registry.unified import contract
from arch.topos.gov.node.anchor import EpochManager
from arch.xor.judger import PureJudger, Signal, Residue
from arch.contract.protocol import proto, BASE_LOOP
from arch.proto.event.network import MultiEventFlow
from arch.proto.event.psi import PsiEvent, PsiCarrier, CarrierType, PhaseField
from phase.dynamics.flow.executor import dispatch_flow_cli

log = get_emitter("judgment.flow")

class JudgmentFlow(MultiEventFlow[PsiEvent, PureJudger]):
    def __init__(self, node_name: str, workspace_path: str):
        super().__init__()
        ## 텐션 평가 및 필드(Field) 관리자
        self.judger = PureJudger()
        
        ## 실행 결과를 계보(Lineage)에 각인할 앵커 노드
        self.anchor = EpochManager(
            name=node_name,
            path=workspace_path,
            runner=lambda p, msg, apply: f"state_{int(time.time() * 1000)}" # Mock Runner
        )

    @proto(BASE_LOOP)
    def execute_flow(self, initial_flow: PsiEvent) -> PureJudger:
        """@flow: Ψ → Interference(Signal vs Residue) → Φ' → Lineage Commit → Attractor"""
        log.info(f"[*] Initiating Pure judgment Flow (Source: {initial_flow.source_id})")
        
        payload = initial_flow.payload
        pressure_factor = payload.get("recognition_strength", 0.8) * payload.get("replication_rate", 1.5)
        resistance = payload.get("methylation_level", 0.2)
        max_steps = payload.get("steps", 50)

        cycle = 0
        is_unstable = True
        reentry_msg = "Initial topological injection"
        era_id = f"era_{initial_flow.event_id}"

        while is_unstable and cycle < max_steps:
            cycle += 1
            
            ## 신호(Signal) 및 파편(Residue) 생성
            current_signal = Signal(
                source=initial_flow.symbol,
                pressure=pressure_factor,
                frequency="high" if pressure_factor > 1.0 else "low",
                payload=reentry_msg
            )
            
            residues = []
            effective_cleavage = pressure_factor - resistance
            if random.random() < effective_cleavage:
                residues.append(Residue(
                    topos_path=f"field.cycle.{cycle}",
                    dissonance_type="cleavage_rupture",
                    content="Phase topology disrupted by external pressure."
                ))
                pressure_factor *= 0.5  # 에너지 감쇠
            else:
                pressure_factor *= 1.1  # 에너지 증폭 (Replication)

            ## 장(Field) 평가 및 안정화 판정
            is_unstable, reentry_msg = self.judger.integrate(current_signal, residues, cycle)
            
            ## 계보(Lineage) 각인 - AnchorNode를 통해 현재 사이클의 장(Field) 상태를 디스크에 기록
            commit_msg = (
                f"[Cycle {cycle}] Field Energy: {self.judger.phi_prime.potential_energy:.2f} | "
                f"Residues: {len(residues)} | State: {'Evolving' if is_unstable else 'Collapsed'}"
            )
            self.anchor.inscribe(
                anchor_id=era_id,
                parent_anchor_id=None,
                parent_commit_id=getattr(self, "_last_commit", "0000000"),
                message=commit_msg,
                apply=True
            )
            self._last_commit = f"cycle_{cycle}"
            time.sleep(0.01)

        log.info(f"[*] Flow Collapsed. Final projection: {self.judger.get_projection()}")
        return self.judger


@contract.flow(name="flow.judgment", entry="flow.judgment")
def judgment_entry(cli_args: list = None, **payload) -> Dict[str, Any]:
    carrier = PsiCarrier(
        kind="judgment_injection",
        tag="judgment",
        payload=payload,
        carrier_type=CarrierType.RECURSIVE,
        target_field=PhaseField.INTERFERENCE
    )
    initial_event = PsiEvent(
        event_id=f"psi_{int(time.time())}",
        parent_id=None,
        source_id="external_cli",
        scope="global",
        tick=0,
        carrier=carrier
    )
    
    ## Flow 초기화 및 실행
    flow_engine = JudgmentFlow(node_name="judgment_core", workspace_path="./workspace")
    final_judger = flow_engine.execute_flow(initial_event)
    return final_judger.get_projection()

if __name__ == "__main__":
    dispatch_flow_cli(
        command_name="flow.judgment", 
        entry_func=judgment_entry, 
        file_path=__file__
    )