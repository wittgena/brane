# phase.dynamics.loop.carrier
## @lineage: arch.proto.loop.carrier
## @lineage: arch.flow.dynamics.carrier
## @lineage: cognitive.flow.dynamics.carrier
## @lineage: cognitive.dynamics.carrier
## @lineage: topos.dynamics.carrier
from __future__ import annotations
import asyncio
from arch.proto.event.next import next_id
from typing import List, Dict, Optional, Any
from arch.contract.base.executor import BaseExecutor
from arch.xor.manifold.cont import XeCont

class LoopCarrier(BaseExecutor):
    """
    @role: self-driven Ψ loop generator
    @flow: 각 Tick마다 Snowflake ID를 새로 생성하여 정밀한 순서 보장
    """
    def __init__(self, xe: XeCont, max_ticks: int = 100, interval: float = 0.1):
        super().__init__()
        self.xe = xe
        self.tick = 0
        self.max_ticks = max_ticks
        self.interval = interval

    async def execute(self, psi: Any) -> List[Any]:
        out = []
        ## 현재 틱(psi) 처리 (위상 장 흡수 및 평가)
        xe_out = await self.xe.execute(psi)
        out.extend(xe_out) ## 현재 결과는 Actuator로 보내서 Surface 업데이트

        ## 다음 틱(Tick) 생성 및 재귀적 발행
        if self.tick < self.max_ticks:
            await asyncio.sleep(self.interval)
            next_psi = psi.__class__(
                event_id=next_id(), 
                parent_id=getattr(psi, "event_id", None),
                source_id="loop.carrier",
                scope=getattr(psi, "scope", "GLOBAL"),
                carrier=getattr(psi, "carrier", None),
                phase_id=getattr(self.xe, 'phase_id', 0),
                tick=self.tick + 1,
                context=getattr(psi, "context", {}).copy()
            )
            
            ## 핵심 해결책: 리턴(out.append)하지 않고, Node의 Bus로 직접 밀어넣어 재순환시킴
            if hasattr(self, "node") and self.node:
                await self.node.bus.publish(next_psi)
            else:
                ## 폴백: 노드가 바인딩되지 않았다면 기존처럼 리턴 (테스트용)
                out.append(next_psi) 
            self.tick += 1
        return out