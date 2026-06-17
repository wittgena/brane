# arch.topos.node.proxy
## @lineage: phase.topos.node.proxy
## @lineage: topos.state.proxy
import time
import uuid
import asyncio
import logging
import random
import json
from typing import Optional, Any
from watcher.plane.emitter import get_emitter
from arch.proto.event.psi import PsiEvent
from arch.proto.phase.flow import PhaseFlow

log = get_emitter("state.proxy")

class StateProxy:
    def __init__(self, role: str, target_node_id: str, runtime, main_loop: asyncio.AbstractEventLoop):
        self.role = role
        self.target_node_id = target_node_id
        self.runtime = runtime
        self.main_loop = main_loop

    async def _dispatch_async(self, flow: PhaseFlow):
        try:
            # PsiEvent를 활용한 메시지 패키징 (시스템의 PIR 인터페이스 규격에 맞게 조정 가능)
            event_payload = json.dumps({
                "target": self.target_node_id,
                "role": self.role,
                "flow_payload": flow.payload,
                "flow_aspect": getattr(flow, "aspect", "default")
            })
            
            # 대상 노드가 수신하는 고유 Redis List(Queue)로 Push
            target_queue = f"runtime:queue:{self.target_node_id}"
            await self.runtime.bus.lpush(target_queue, event_payload)
            log.debug(f"[RemoteProxy] Successfully dispatched flow to {self.target_node_id} (Role: {self.role})")
            
        except Exception as e:
            log.error(f"[RemoteProxy] Dispatch failed for {self.target_node_id}: {e}")
            raise

    def __call__(self, flow: PhaseFlow):
        future = asyncio.run_coroutine_threadsafe(
            self._dispatch_async(flow),
            self.main_loop
        )
        return future

class DistributedNodePool:
    def __init__(self, runtimeNode):
        self.runtime = runtimeNode
        try:
            self.main_loop = asyncio.get_running_loop()
        except RuntimeError:
            self.main_loop = asyncio.get_event_loop()

    @property
    def bus(self):
        """런타임 노드에서 항상 최신의 redis 인스턴스를 가져옵니다."""
        if self.runtime.bus is None:
            # 아직 바인딩되지 않은 경우에 대한 방어 로직 (선택)
            log.warning("[NodePool] Accessing redis before node.start().")
        return self.runtime.bus

    def get(self, role: str) -> StateProxy:
        try:
            # 기존 _resolve_target 대신, 대기/생성이 포함된 래퍼 코루틴 호출
            future = asyncio.run_coroutine_threadsafe(
                self._resolve_with_retry_or_spawn(role), 
                self.main_loop
            )
            
            # 대기 시간(timeout)을 넉넉히 줍니다 (예: 최대 15초 대기)
            target_node_id = future.result(timeout=15.0) 
            
            return StateProxy(role, target_node_id, self.runtime, self.main_loop)
            
        except Exception as e:
            log.error(f"NodePool totally failed to provide capability '{role}': {e}")
            raise

    async def _resolve_with_retry_or_spawn(self, role: str, max_retries=3, delay=2.0) -> str:
        """
        [1] 일정 횟수만큼 Redis를 폴링하며 워커 등록대기
        [2] 실패 시, Fallback 워커를 스스로 로드 (Cold Start).
        """
        for attempt in range(max_retries):
            target = await self._resolve_target(role)
            if target:
                return target
                
            log.warning(f"[Registry Miss] No agents for '{role}'. Retrying in {delay}s... ({attempt+1}/{max_retries})")
            await asyncio.sleep(delay)

        log.warning(f"[Auto-Provision] Exhausted retries for '{role}'. Spawning a local fallback agent...")
        return await self._spawn_fallback_agent(role)

    async def _spawn_fallback_agent(self, role: str) -> str:
        """요구되는 역량을 수행할 수 있는 임시 워커를 생성하여 Redis에 등록"""
        fallback_id = f"node-fallback-{role}-{uuid.uuid4().hex[:6]}"
        
        ## Redis 글로벌 인덱스에 역량 강제 등록
        capability_key = f"capability:{role}"
        await self.bus.sadd(f"runtime:index:emits:{capability_key}", fallback_id)
        
        ## 생존(Heartbeat) 기록 (임시로 60초 부여)
        await self.bus.set(f"runtime:heartbeat:{fallback_id}", int(time.time()), ex=60)
        log.info(f"[Auto-Provision] Fallback agent '{fallback_id}' successfully spawned and registered.")
        
        return fallback_id

    async def _resolve_target(self, role: str) -> Optional[str]:
        capability_key = f"capability:{role}"
        index_key = f"runtime:index:emits:{capability_key}"
        
        retry_count = 0
        while self.bus is None and retry_count < 5:
            log.info("[NodePool] Waiting for Redis to be initialized...")
            await asyncio.sleep(1.0)
            retry_count += 1

        if self.bus is None:
            log.error("[NodePool] Redis is not available after wait.")
            return None

        capable_nodes = await self.bus.smembers(index_key)
        if not capable_nodes:
            return None
            
        alive_nodes = []
        for n_id in capable_nodes:
            n_id_str = n_id.decode('utf-8') if isinstance(n_id, bytes) else n_id
            if await self.bus.exists(f"runtime:heartbeat:{n_id_str}"):
                alive_nodes.append(n_id_str)
                
        if not alive_nodes:
            return None

        return random.choice(alive_nodes)
