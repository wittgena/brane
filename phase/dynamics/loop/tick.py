# phase.dynamics.loop.tick
## @lineage: phase.reflect.loop.tick
## @lineage: cognitive.reflect.loop.tick
## @lineage: cognitive.rhythm.loop.tick
import asyncio
import json
import redis.asyncio as redis_async
from arch.proto.event.psi import PsiEvent, PsiCarrier

async def rhythm_loop_tick(event_bus, redis_url: str = "redis://redis:6379", channel: str = "rhythm.heart"):
    """@desc: Redis에서 심장 박동 이벤트를 수신하여 내부 EventBus로 중계"""
    r = redis_async.from_url(redis_url, decode_responses=True)
    pubsub = r.pubsub()
    await pubsub.subscribe(channel)
    print(f"[System] Syncing with Heartbeat Field on channel: {channel}")

    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue

            ## Redis로부터 JSON 수신 및 역직렬화
            raw_data = json.loads(message["data"])
            
            ## PsiEvent 객체 재구성
            carrier_data = raw_data.get("carrier", {})
            event = PsiEvent(
                event_id=raw_data.get("event_id"),
                parent_id=raw_data.get("parent_id"),
                source_id=raw_data.get("source_id"),
                scope=raw_data.get("scope"),
                tick=raw_data.get("tick"),
                carrier=PsiCarrier(
                    kind=carrier_data.get("kind"),
                    tag=carrier_data.get("tag"),
                    payload=carrier_data.get("payload")
                ),
                context=raw_data.get("context")
            )

            ## 특정 박동(예: SYSTOLE - 수축기)일 때만 메트릭 갱신 틱으로 인정하거나, 모든 박동을 전달
            await event_bus.publish(event)
    except asyncio.CancelledError:
        await pubsub.unsubscribe(channel)
        print("[System] Heartbeat sync stopped.")
    except Exception as e:
        print(f"[System Error] Heartbeat loop failure: {e}")