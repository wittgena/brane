# phase.runtime.daemon
## @lineage: phase.node.daemon
import asyncio
import json
import time
import random
from abc import ABC, abstractmethod
from typing import Optional
import redis.asyncio as redis_async
from watcher.plane.emitter import get_emitter
from phase.runtime.surface.sensor import sense_once
from arch.proto.event.psi import PsiEvent, PsiCarrier
from arch.proto.event.bus import AsyncEventBus
from phase.runtime.dispatcher import Dispatcher
from phase.runtime.receptor.bootstrap import receptor_bootstrap

SENSOR_INTERVAL = 1.0

class AbstractDaemon(ABC):
    """@loop.contract: 스스로의 생명주기를 가지는 독립적 주기 컴포넌트"""
    def __init__(self, name: str):
        self.name = name
        self.running = False
        self.task: Optional[asyncio.Task] = None
        self.log = get_emitter(f"daemon.{name.lower()}", phase="SYSTEM")

    async def start(self) -> asyncio.Task:
        self.running = True
        self.task = asyncio.create_task(self.run(), name=self.name)
        return self.task

    async def stop(self):
        self.running = False
        if self.task and not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

    @abstractmethod
    async def run(self):
        pass

class SensorDaemon(AbstractDaemon):
    """@psi.observe: surface → bus"""
    def __init__(self, redis: redis_async.Redis, bus: AsyncEventBus):
        super().__init__("Sensor")
        self.redis = redis
        self.bus = bus

    async def run(self):
        self.log.info("Sensor loop started. Observing state space.")
        while self.running:
            try:
                signals = await sense_once(self.redis)
                for psi in signals:
                    await self.bus.publish(psi) 
                await asyncio.sleep(SENSOR_INTERVAL)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.log.error(f"Sensor Error: {e}")
                await asyncio.sleep(2)

class CaptureDaemon(AbstractDaemon):
    """@psi.capture: global queue → dispatcher"""
    def __init__(self, redis: redis_async.Redis, dispatcher: Dispatcher, node: 'NodeRuntime', idle_timeout: int):
        super().__init__("Capture")
        self.redis = redis
        self.dispatcher = dispatcher
        self.node = node
        self.base_timeout = idle_timeout  
        self.idle_timeout = idle_timeout
        self.last_active_time = time.time()

    async def run(self):
        self.log.info(f"Capture loop started (Idle Timeout: {self.idle_timeout}s)")
        while self.running:
            try:
                res = await self.redis.brpop("runtime:queue", timeout=1.0)
                if res:
                    _, data = res
                    event_dict = json.loads(data)
                    if 'carrier' in event_dict and isinstance(event_dict['carrier'], dict):
                        event_dict['carrier'] = PsiCarrier(**event_dict['carrier'])
                    
                    psi = PsiEvent(**event_dict)
                    self.last_active_time = time.time()
                    self.idle_timeout = self.base_timeout 
                    await self.dispatcher.send(psi)
                else:
                    if time.time() - self.last_active_time > self.idle_timeout:
                        active_nodes = await self.redis.keys("runtime:heartbeat:*")
                        if len(active_nodes) <= 1:
                            decayed = self.idle_timeout * 0.9
                            jitter = random.uniform(-5.0, 5.0)
                            self.idle_timeout = max(10.0, decayed + jitter)
                            self.last_active_time = time.time()
                            self.log.warn(
                                f"Last node standing. Evaporation aborted. "
                                f"Idle timeout mutated to {self.idle_timeout:.1f}s"
                            )
                        else:
                            self.log.warn(f"Idle for {self.idle_timeout:.1f}s. Self-evaporating...")
                            asyncio.create_task(self.node.shutdown())
                            break
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.log.error(f"Capture Error: {e}")
                await asyncio.sleep(1)

class HeartbeatDaemon(AbstractDaemon):
    """@phase.liveness: temporal presence 유지"""
    def __init__(self, redis: redis_async.Redis, node_id: str):
        super().__init__("Heartbeat")
        self.redis = redis
        self.node_id = node_id

    async def run(self):
        try:
            while self.running:
                await self.redis.set(f"runtime:heartbeat:{self.node_id}", int(time.time()), ex=10)
                await self.redis.set("runtime:active", int(time.time()), ex=10)
                await asyncio.sleep(3)
        except asyncio.CancelledError:
            pass

class SignalDaemon(AbstractDaemon):
    """@control.inbound: external signal → runtime control"""
    def __init__(self, redis: redis_async.Redis, node: 'NodeRuntime'):
        super().__init__("Signal")
        self.redis = redis
        self.node = node

    async def run(self):
        pubsub = self.redis.pubsub()
        await pubsub.subscribe("runtime:signal")
        try:
            async for msg in pubsub.listen():
                if not self.running:
                    break
                if msg["type"] == "message":
                    parsed = json.loads(msg["data"])
                    if parsed.get("type") == "shutdown":
                        asyncio.create_task(self.node.shutdown())
                        break
        except asyncio.CancelledError:
            pass
        finally:
            await pubsub.unsubscribe("runtime:signal")
            await pubsub.close()

class ReceptorDaemon(AbstractDaemon):
    """@membrane.leader: 스웜(Swarm) 중 단 하나의 노드만 물리적 멤브레인(Watchdog)을 담당하도록 하는 리더 선출 데몬"""
    def __init__(self, redis: redis_async.Redis, node_id: str, watch_dir: str):
        super().__init__("Receptor")
        self.redis = redis
        self.node_id = node_id
        self.watch_dir = watch_dir
        self.lock_key = "runtime:receptor:leader"
        self.receptor_task: Optional[asyncio.Task] = None

    async def run(self):
        self.log.info("Receptor daemon initiated. Engaging in leader election...")
        try:
            while self.running:
                ## 분산 락 획득 시도 (TTL 6초)
                acquired = await self.redis.set(self.lock_key, self.node_id, nx=True, ex=6)
                
                if not acquired:
                    current_leader = await self.redis.get(self.lock_key)
                    if current_leader == self.node_id:
                        await self.redis.expire(self.lock_key, 6)
                        acquired = True

                ## 위상(역할) 실행
                if acquired:
                    if self.receptor_task is None or self.receptor_task.done():
                        self.log.warn(f"[{self.node_id}] Acquired Membrane Leadership. Bootstrapping Receptor...")
                        self.receptor_task = asyncio.create_task(receptor_bootstrap(self.watch_dir))
                else:
                    ## leadership을 상실했을 때의 처리
                    if self.receptor_task and not self.receptor_task.done():
                        self.log.warn(f"[{self.node_id}] Lost Membrane Leadership. Shutting down local Receptor...")
                        self.receptor_task.cancel()
                        
                        ## leadership 교체 시에도 이전 멤브레인의 완전한 철거를 기다림
                        try:
                            await self.receptor_task
                        except asyncio.CancelledError:
                            pass
                        self.receptor_task = None

                await asyncio.sleep(2)
                
        except asyncio.CancelledError:
            self.log.warn("ReceptorDaemon received cancellation signal.")
        except Exception as e:
            self.log.error(f"ReceptorDaemon Error: {e}")
        
        finally:
            ## Graceful Teardown
            if self.receptor_task and not self.receptor_task.done():
                self.log.warn("Tearing down Membrane (Watchdog OS Threads)...")
                self.receptor_task.cancel()
                try:
                    ## cancel 후 태스크가 완전히 끝날 때(observer.join() 완료)까지 대기
                    await self.receptor_task 
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    self.log.error(f"Error during Membrane teardown: {e}")
            
            ## 내가 리더로서 종료되는 것이라면 락을 해제하여 타 노드에 즉시 인계
            try:
                if await self.redis.get(self.lock_key) == self.node_id:
                    await self.redis.delete(self.lock_key)
            except Exception:
                pass
            
            self.log.info("ReceptorDaemon successfully evaporated.")
