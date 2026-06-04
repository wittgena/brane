# bound.scan.phase
## @lineage: debug.exam.scan.phase
## @lineage: meta.flow.scan.phase
## @lineage: meta.scan.phase
## @lineage: meta.phase.observer
import asyncio
import json
import time
import redis.asyncio as redis_async
from typing import Optional, Dict, Any
from phase.bind.resolver import resolve_channel
from watcher.plane.emitter import get_emitter

class PhaseScanner:
    """
    @role: Phase Scanner
    @desc:
    - 분산된 NodeRuntime 매니폴드의 활성 상태(State)와 심박(Heartbeat) 스캔
    - Perturbator의 교란이나 내부 압력에 의한 구조적 파열(Rupture) 관측
    - 글로벌 로그 스트림 바인딩
    """
    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self.redis_url = redis_url
        self.redis: Optional[redis_async.Redis] = None
        self.log = get_emitter("observer.phase", phase="meta")

    async def connect(self):
        self.redis = await redis_async.from_url(self.redis_url, decode_responses=True)
        self.log.info("Topology Observatory online. Tuning into global manifold...")

    async def scan_active_nodes(self):
        """@desc: 현재 위상 공간에 등록된 NodeRuntime들의 생존 여부와 역량 스캔"""
        keys = await self.redis.keys("runtime:node:*")
        self.log.info(f"\n--- [Topos] Active Nodes in Manifold: {len(keys)} ---")

        for key in keys:
            node_data = await self.redis.hgetall(key)
            node_id = node_data.get("node_id", "UNKNOWN")
            started_at = float(node_data.get("started_at", time.time()))
            uptime = time.time() - started_at

            # HeartbeatDaemon이 남기는 심박수 확인
            last_ping = await self.redis.get(f"runtime:heartbeat:{node_id}")
            status = "HEALTHY" if last_ping else "STALE/ZOMBIE"

            # Node의 Capability 척도 계산
            caps = node_data.get("capabilities", "{}")
            try:
                caps_dict = json.loads(caps)
                cap_count = len(caps_dict)
            except Exception:
                cap_count = 0

            self.log.signal(
                f" └─ {node_id} | Uptime: {uptime:.1f}s | Status: {status} | Bounds: {cap_count}"
            )

    async def stream_consciousness(self):
        """@desc: 모든 노드의 사유 과정(Log Stream)과 파열 경고(Alert)를 Pub/Sub으로 수신"""
        pubsub = self.redis.pubsub()
        # 로거가 방출하는 스트림과 시스템 붕괴 알림 채널 동시 구독
        await pubsub.psubscribe("system:logs:*", "system:alerts")
        self.log.info("Subscribed to global consciousness stream. Waiting for resonance...")

        async for msg in pubsub.listen():
            if msg["type"] != "pmessage":
                continue

            channel = msg["channel"]
            try:
                data = json.loads(msg["data"])
                node_id = data.get("node_id", "system")

                if "alerts" in channel:
                    # 구조적 파열(Rupture/Shutdown) 감지 시 강한 시각적 알림
                    payload = data.get("payload", {})
                    self.log.crit(f"⚡ [RUPTURE DETECTED] Phase collapse in {node_id}: {payload}")
                else:
                    # 일반 로그 바인딩
                    level = data.get("level", "INFO")
                    message = data.get("message", "")
                    # 일반 출력 포맷핑
                    print(f"[{level}] <{node_id}> : {message}")
            except Exception:
                # JSON 디코딩 실패 등 예외 처리 (잔여물 무시)
                pass

    async def watch(self, scan_interval: float = 5.0):
        """@flow: 로그 스트림(Push)은 백그라운드 태스크로 띄우고, 노드 스캔(Pull)은 주기적으로 실행"""
        stream_task = asyncio.create_task(self.stream_consciousness())
        try:
            while True:
                await self.scan_active_nodes()
                await asyncio.sleep(scan_interval)
        except asyncio.CancelledError:
            stream_task.cancel()

if __name__ == "__main__":
    async def main():
        obs = PhaseScanner()
        await obs.connect()
        await obs.watch(scan_interval=10.0)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n## Observatory stopped. Viewport closed.")