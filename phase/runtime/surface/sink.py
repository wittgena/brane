# phase.runtime.surface.sink
## @lineage: arch.model.surface.sink
import os
import json
import aiohttp
from abc import ABC, abstractmethod
from typing import AsyncGenerator
import redis.asyncio as redis_async

class EmitterSink(ABC):
    @abstractmethod
    async def set(self, key: str, payload: dict):
        pass

    @abstractmethod
    async def delete(self, key: str):
        pass

    async def get_control_flag(self, key: str):
        return None

    async def close(self):
        pass

    @abstractmethod
    async def publish(self, channel: str, payload: str):
        """방출(Emission)을 위한 브로드캐스트 인터페이스"""
        pass

    @abstractmethod
    async def subscribe(self, channel: str) -> AsyncGenerator[str, None]:
        """
        수신(Reception)을 위한 구독 인터페이스
        @flow: Async Iterator를 통해 이벤트 루프 블로킹 없이 메시지 스트림 제공
        """
        pass

class RedisSink(EmitterSink):
    def __init__(self, host="localhost", port=6379, db=0):
        self.redis = redis_async.Redis(host=host, port=port, db=db)

    async def set(self, key, payload):
        await self.redis.set(key, str(payload))

    async def delete(self, key):
        await self.redis.delete(key)

    async def get_control_flag(self, key):
        val = await self.redis.get(key)
        return val.decode() if val else None

    async def close(self):
        await self.redis.close()
    
    async def publish(self, channel: str, payload: str):
        await self.redis.publish(channel, payload)

    async def subscribe(self, channel: str) -> AsyncGenerator[str, None]:
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(channel)
        
        # async for를 지원하기 위해 비동기 제너레이터(yield) 사용
        async for message in pubsub.listen():
            if message["type"] == "message":
                data = message["data"]
                yield data.decode('utf-8') if isinstance(data, bytes) else data

class FileSink(EmitterSink):
    def __init__(self, base_dir="/tmp/psi_surface"):
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)

    def _path(self, key):
        return os.path.join(self.base_dir, f"{key}.json")

    async def set(self, key, payload):
        # 향후 aiofiles 도입을 권장하지만, 일단 동기 I/O 유지
        with open(self._path(key), "w") as f:
            json.dump(payload, f)

    async def delete(self, key):
        path = self._path(key)
        if os.path.exists(path):
            os.remove(path)

    async def publish(self, channel: str, payload: str):
        # File 방식에서의 Pub/Sub은 꼬리물기(tail) 등으로 구현해야 하므로 임시 패스
        pass

    async def subscribe(self, channel: str) -> AsyncGenerator[str, None]:
        # NotImplemented. 향후 watchdog 이나 inotify 로 파일 변경 스트림 구현 가능
        yield "" 

class ApiSink(EmitterSink):
    def __init__(self, endpoint):
        self.endpoint = endpoint
        self.session = aiohttp.ClientSession()

    async def set(self, key, payload):
        await self.session.post(f"{self.endpoint}/{key}", json=payload)

    async def delete(self, key):
        await self.session.delete(f"{self.endpoint}/{key}")

    async def close(self):
        await self.session.close()

    async def publish(self, channel: str, payload: str):
        ## Webhook이나 SSE(Server-Sent Events) 트리거 용도
        await self.session.post(f"{self.endpoint}/publish/{channel}", json={"payload": payload})

    async def subscribe(self, channel: str) -> AsyncGenerator[str, None]:
        ## SSE(Server-Sent Events)나 WebSocket을 통한 스트리밍 구현 자리
        yield ""