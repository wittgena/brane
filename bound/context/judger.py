# bound.context.judger
## @lineage: debug.context.judger
## @lineage: gov.exam.context.judger
## @lineage: bound.watcher.context.judger
## @lineage: bound.watcher.cont.judger
## @lineage: bound.reflect.cont.judger
from typing import List, Dict, Any
from arch.contract.registry.unified import contract
from arch.proto.phase.flow import ProtoFlow
from watcher.plane.emitter import get_logger
from gov.scope.manager import managed_scope
from phase.bind.folding import folding
from arch.xor.judger import PureJudger, Signal, Residue
from arch.proto.context.signature import ProtoSignature, In, Out
from gov.scope.thch import ThCh 

log = get_logger("context.judger")

class TranslateSignal(ProtoSignature):
    """의미론적 텍스트를 구조적 긴장(Signal)으로 번역"""
    raw_input: str = In()
    structural_signal: str = Out(desc="고압축 구조적 신호 (Payload)")

class ExtractResidue(ProtoSignature):
    """장의 상태와 신호를 비교하여 충돌 파편(xe) 추출"""
    field_state: str = In()
    signal_payload: str = In()
    ruptures: str = Out(desc="충돌 파편들의 쉼표 구분 목록, 없으면 'stable' 반환")

@contract.ator("foldbox.judger")
class FoldboxJudger:
    """@ex.surface: 위상에 의해 호출되며, 물리 스코프를 열어 Attractor 탐색 루프를 수행"""
    
    async def execute(self, flow: ProtoFlow) -> ProtoFlow:
        initial_input = flow.payload.get("instruction", "Genesis Signal")
        model_name = flow.payload.get("model", "local-gemma-3")
        core_judger = PureJudger()

        with managed_scope(use_psi=True, use_thch=True, psi_model=model_name) as surface:
            with folding(self, re_entry_limit=3) as protected_self:
                final_state = await protected_self._seek_attractor(core_judger, initial_input)
                
        return ProtoFlow(
            payload={
                "status": "success", 
                "projection": final_state, 
                "tension": core_judger.phi_prime.potential_energy
            },
            aspect=flow.aspect
        )

    async def _seek_attractor(self, core_judger: PureJudger, initial_input: str):
        """실제 시간 축(Cycle)을 돌리며 프록시 엔진과 기저 엔진을 교차시키는 루프"""
        current_input = initial_input
        cycle = 0
        
        translator = ThCh(TranslateSignal)
        extractor = ThCh(ExtractResidue)
        
        while True:
            cycle += 1
            log.info(f"## Cycle {cycle}: Attractor Seeking (Tension: {core_judger.phi_prime.potential_energy:.4f}) ---")
            trans_res = translator(raw_input=current_input)
            signal = Signal(
                source="re-entry" if cycle > 1 else "origin",
                pressure=1.0 / cycle,
                frequency="high-interference" if "xe" in current_input else "stable",
                payload=trans_res.structural_signal
            )
            
            ext_res = extractor(
                field_state=str(core_judger.get_projection()), 
                signal_payload=signal.payload
            )
            
            xe_list = []
            if "stable" not in ext_res.ruptures.lower():
                for r_text in ext_res.ruptures.split(','):
                    if r_text.strip():
                        xe_list.append(Residue(
                            topos_path="surface.node", 
                            dissonance_type="interference", 
                            content=r_text.strip()
                        ))

            ## 기저 물리 엔진(PureJudger)과의 통합 및 평형 도달 여부 판단
            should_continue, next_input = core_judger.integrate(signal, xe_list, cycle)
            if not should_continue:
                log.info(f"## Attractor Found at Cycle {cycle}")
                break
            current_input = next_input
        return core_judger.get_projection()