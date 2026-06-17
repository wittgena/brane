# arch.xor.manifold.cont
## @lineage: phase.dynamics.manifold.cont
## @lineage: arch.proto.manifold.cont
## @lineage: arch.model.manifold.cont
## @lineage: topos.model.manifold.cont
## @lineage: cognitive.dynamics.xe
## @lineage: topos.dynamics.xe
from __future__ import annotations
import asyncio
from arch.proto.event.next import next_id, next_phase_id, parse_id, parse_phase_id 
from typing import List, Dict, Optional, Any
from arch.contract.base.executor import BaseExecutor
from arch.contract.registry.unified import registry

class PhaseField(type(BaseExecutor)):
    """@phase.bound: 클래스 생성 시점에 고유한 Snowflake ID 부여"""
    def __new__(mcs, name, bases, namespace):
        # 4글자 해시 대신 Snowflake ID를 사용하여 글로벌 고유성 확보
        namespace['bound_id'] = f"bound.{next_id()}"
        return super().__new__(mcs, name, bases, namespace)

class XeCont(BaseExecutor, metaclass=PhaseField):
    """
    @entity: autonomous phase carrier
    @flow: Snowflake로 선후관계를, PhaseId로 상태 벡터를 기록
    """
    def __init__(self, bound, ex: str = "void", origin: str = "void"):
        super().__init__()
        ## trace_id를 Snowflake로 변경하여 시간순 정렬 가능하게 함
        self.trace_id = next_id() 
        self.phase_id = 0 # 현재 위상 상태 저장
        self.ex = ex
        self.origin = origin
        self.bound = bound

    async def execute(self, psi: Any) -> List[Any]:
        ## step.1: Ψ → ∂Φ (흡수 및 위상 업데이트)
        batch_payload = [{"payload": psi.symbol}]
        self.bound.absorb(batch_payload)
        
        # 현재 bound의 물리량으로부터 Phase ID 갱신
        self.phase_id = next_phase_id(
            topo=int(getattr(self.bound, 'topology', 0)), 
            press=int(getattr(self.bound, 'pressure', 0))
        )

        ## step.2: τ evaluation
        decision = self.bound.evaluate()
        
        if decision == "DEPOSIT":
            # Rupture(단절) 발생 시 Phase ID의 Epoch를 전환하여 계보를 분리
            self.phase_id = next_phase_id(
                topo=int(self.bound.topology), 
                press=int(self.bound.pressure), 
                rupture=True
            )
            
            self.bound.commit()
            ext_base = self._ext__()
            
            ## 로그 출력 시에도 정렬 가능한 ID 사용
            print(f"\n[Rupture] {self.trace_id} (Phase:{hex(self.phase_id)}) -> {ext_base.trace_id}")
            self.ex = ext_base.ex
            self.origin = ext_base.trace_id
        else:
            # Saturation(포화) 상태 로그
            pass

        ## step.3: ID 주입 (psi 이벤트에 현재의 Snowflake와 Phase 정보를 바인딩)
        psi.event_id = next_id()
        psi.phase_id = self.phase_id
        return [psi]

    def _ext__(self) -> 'XeCont':
        return XeCont(
            bound=self.bound,
            ex=f"Base.bind(inversion.overflow.{self.ex})",
            origin=self.trace_id
        )