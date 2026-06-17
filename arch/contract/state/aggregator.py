# arch.contract.state.aggregator
## @lineage: topos.contract.state.aggregator
## @lineage: phase.runtime.state.aggregator
## @lineage: phase.node.state.aggregator
from dataclasses import dataclass, field
from typing import Dict, Any, List
import redis.asyncio as redis_async
from arch.proto.event.psi import PsiCarrier
from phase.runtime.interpreter import NodeInterpreter

@dataclass
class CoreState:
    """@state.contract: 결정론적 코어 상태의 구조화된 스냅샷"""
    phase: str
    version: str
    meta: Dict[str, Any] = field(default_factory=dict)

@dataclass
class InternalContext:
    """@worker.payload: 내부 워커가 의사결정을 내리기 위해 참조하는 런타임 컨텍스트"""
    event: PsiCarrier
    state: CoreState
    surface_signals: Dict[str, Any]

class KernelStateAggregator:
    """@context: runtime state + surface signals → InternalContext (Worker Payload)"""
    def __init__(self, interpreter: NodeInterpreter, redis: redis_async.Redis):
        self.machine = interpreter
        self.redis = redis

    def snapshot_state(self) -> CoreState:
        """@state.snapshot: 동적 상태를 불변하는 스냅샷으로 동결(Freezing)"""
        return CoreState(
            phase=self.machine.phase,
            version=self.machine.anchor.version,
            meta={} 
        )

    async def retrieve_surface_signals(self, psi: PsiCarrier) -> Dict[str, Any]:
        """@signal.retrieve: 블로킹 없는(Scan) 구조화된 표면 데이터 수집"""
        signals: Dict[str, Any] = {}
        pattern = f"*{psi.tag.split(':')[0]}*".encode('utf-8')

        try:
            # 안전한 조회를 위해 KEYS 대신 비동기 SCAN 사용 (병목 해소)
            cursor = b'0'
            collected_keys = []
            while cursor:
                cursor, keys = await self.redis.scan(cursor=cursor, match=pattern, count=100)
                collected_keys.extend(keys)
                if len(collected_keys) >= 5: # Limit boundary
                    break
            
            for k in collected_keys[:5]:
                val = await self.redis.get(k)
                if val:
                    signals[k.decode('utf-8')] = val.decode('utf-8')
                    
        except Exception as e:
            # Metalog 또는 Logger를 통한 우아한 예외 처리
            print(f"[RuntimeStateAggregator] signal retrieval error: {e}")

        return signals

    async def build_context(self, psi: PsiCarrier) -> InternalContext:
        """@context.assemble: 내부 워커용 캡슐 조립"""
        state = self.snapshot_state()
        signals = await self.retrieve_surface_signals(psi)
        return InternalContext(
            event=psi,
            state=state,
            surface_signals=signals
        )