# phase.dynamics.rhythm.coupler
## @lineage: phase.reflect.rhythm.coupler
## @lineage: cognitive.reflect.rhythm.coupler
## @lineage: cognitive.rhythm.coupler
import json
from typing import Optional
from watcher.plane.emitter import get_emitter

log = get_emitter("rhythm.coupler")

class RhythmCoupler:
    def __init__(self, loop, redis, bus=None):
        self.loop = loop
        self.redis = redis
        self.bus = bus

    async def start(self):
        pubsub = self.redis.pubsub()

        # 기존 구독 채널 + 자아(Ego)의 발작 채널 추가
        await pubsub.subscribe("rhythm.heart")
        await pubsub.subscribe("phase:decision")
        await pubsub.subscribe("ego:action") # 👈 Ego의 마찰 채널 구독

        log.info("  [Coupler] RhythmCoupler started. Listening to 'rhythm.heart', 'phase:decision', 'ego:action'")

        async for msg in pubsub.listen():
            if msg["type"] != "message":
                continue

            channel = msg["channel"]
            data = json.loads(msg["data"])

            if channel == "ego:action":
                ## PsiEvent JSON 구조에서 캐리어(Carrier) 데이터 추출
                carrier_data = data.get("carrier", {})
                kind = carrier_data.get("kind", "ego:friction")
                payload = carrier_data.get("payload", {})
                
                strength = payload.get("strength", 0.0)
                source = payload.get("source", "unknown")
                
                ## 에고의 스트레스를 시스템 전체에 경고
                log.error(f"  [Coupler] 🔥 자아(Ego) 폭주 감지! [{source}]의 마찰 부하({strength:.2f})를 위상 공간으로 타격합니다.")
                
                ## Resonator의 외부 주입 엔드포인트(emit)를 통해 장력 전이
                if hasattr(self.loop, "emit"):
                    await self.loop.emit(kind, payload)
                continue

            ## observe phase space & feedback rhythm
            if channel == "phase:decision":
                tension = float(data.get("tension", 0.0))

                if tension > 1.2:
                    log.warning(f"  [Coupler] 🚨 위상 장력 과부하 ({tension:.3f})! heart:shock 발행")
                    await self.redis.publish("runtime:signal", json.dumps({"type": "heart:shock"}))
                elif tension < 0.15:
                    log.info(f"  [Coupler] 위상 장력 이완 ({tension:.3f}). heart:pace 발행")
                    await self.redis.publish("runtime:signal", json.dumps({"type": "heart:pace"}))
                continue

            ##외부의 심박/동기화 시그널 주입)
            if channel == "rhythm.heart":
                event_kind = data.get("kind")
                if event_kind and event_kind.startswith("heart:"):
                    log.info(f"  [Coupler] 외부 리듬 주입: {event_kind}")
                    if hasattr(self.loop, "emit"):
                        await self.loop.emit(event_kind, {"strength": 0.5})