# phase.dynamics.rhythm.bridge
## @lineage: phase.reflect.rhythm.bridge
## @lineage: cognitive.reflect.rhythm.bridge
## @lineage: cognitive.rhythm.bridge
## @lineage: topos.bound.rhythm.bridge
import json
from typing import Dict, Any, Optional
import redis.asyncio as redis_async
from arch.proto.event.next import next_id, next_phase_id

class RhythmBridge:
    """
    @role: 시스템의 심장박동 및 외부 통신 어댑터
    글로벌 Snowflake ID와 인과 Phase ID를 동기화하여 전파합니다.
    """
    def __init__(self, redis_url: str, channel: str):
        self.redis = redis_async.from_url(redis_url, decode_responses=True)
        self.channel = channel

    async def emit(self, psi: Any):
        """이벤트를 Snowflake 및 Phase 정보를 담아 Redis로 방출"""
        # 만약 psi에 ID가 없다면 생성하여 주입
        if not getattr(psi, 'event_id', None):
            psi.event_id = next_id()
        
        payload = {
            "event_id": psi.event_id,
            "phase_id": getattr(psi, 'phase_id', 0),
            "kind": getattr(psi, 'kind', 'unknown'),
            "tag": getattr(psi, 'tag', ''),
            "tick": getattr(psi, 'tick', 0),
            "timestamp": parse_id(psi.event_id)['timestamp_ms']
        }
        
        await self.redis.publish(self.channel, json.dumps(payload))