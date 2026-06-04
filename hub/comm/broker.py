# hub.comm.broker
## @lineage: gov.hub.broker
import json
import redis
from pydantic import BaseModel
from typing import Optional, Iterator, Dict, Any
from watcher.plane.emitter import get_emitter

log = get_emitter("hub.broker")

class SporeManifest(BaseModel):
    trial_id: int
    parent_hash: str
    status: str = "PENDING"
    config_uri: str 
    weight_uri: Optional[str] = None
    error_message: Optional[str] = None

class RedisBroker:
    """Redis Streams 및 KV를 활용한 메시지 브로커 및 상태 관리기"""
    def __init__(self, redis_url: str):
        self.client = redis.from_url(redis_url, decode_responses=True)
        self.pending_queue = "nexus:queue:pending"
        self.completed_queue = "nexus:queue:completed"

    def dispatch_task(self, manifest: SporeManifest, timeout_seconds: int = 3600):
        """Scatter: 새 작업을 큐에 밀어넣고, Heartbeat 키를 생성합니다."""
        # 1. 워커들이 가져갈 수 있도록 큐에 추가 (LPUSH 또는 XADD)
        self.client.lpush(self.pending_queue, manifest.model_dump_json())
        
        # 2. 좀비 워커 방지를 위한 TTL 키 설정 (이 시간 내에 완료/연장 안되면 죽은 것으로 간주)
        heartbeat_key = f"nexus:trial:{manifest.trial_id}:heartbeat"
        self.client.setex(heartbeat_key, timeout_seconds, "ALIVE")
        log.info(f"Task dispatched to Redis: Trial {manifest.trial_id}")

    def consume_completed(self) -> Iterator[tuple[str, SporeManifest]]:
        """Harvest: 완료된 작업을 블로킹 방식으로 대기하며 가져옵니다 (BRPOP)."""
        log.info(f"Listening for completed spores on {self.completed_queue}...")
        while True:
            # 타임아웃 0으로 설정하여 무한 대기 (Event-Driven)
            result = self.client.brpop(self.completed_queue, timeout=0)
            if result:
                queue_name, message = result
                manifest = SporeManifest.parse_raw(message)
                yield message, manifest

    def ack_completed(self, trial_id: int):
        """작업이 완전히 처리(DB 반영, Optuna 갱신)된 후 관련 상태를 정리합니다."""
        heartbeat_key = f"nexus:trial:{trial_id}:heartbeat"
        self.client.delete(heartbeat_key)

    def find_zombie_trials(self) -> list[int]:
        """Heartbeat TTL이 만료된(키가 사라진) 진행 중인 trial들을 찾습니다."""
        # 실제 구현 시에는 별도의 Set에 active_trials를 관리하고 교집합을 확인
        pass