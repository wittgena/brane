# phase.runtime.dispatcher
## @lineage: phase.node.dispatcher
import asyncio
import time
from typing import Callable, Optional
from arch.proto.event.psi import PsiType

class Dispatcher:
    def __init__(
        self,
        handler: Callable[[PsiType], Optional[dict]],
        emitter=None,
        broadcaster=None,
        executor=None,
        actuator=None,
        max_queue: int = 1000,
    ):
        self.queue = asyncio.Queue(maxsize=max_queue)
        self.handler = handler
        self.emitter = emitter
        self.broadcaster = broadcaster
        self.executor = executor
        self.actuator = actuator

        self.alive = False
        self.task = None
        self.processed = 0

    async def start(self):
        if self.alive:
            return
        
        # 시작 전 handler 검증
        if not callable(self.handler):
            raise TypeError(f"[Dispatcher] Handler must be callable, got {type(self.handler)}")

        self.alive = True
        self.task = asyncio.create_task(self._run())
        print("[Dispatcher] Online")

    async def _run(self):
        while self.alive:
            psi = await self.queue.get()
            if psi is None:
                break

            try:
                print(f"[ψ] {psi.symbol}")
                
                ## 1. Executor Stage
                if self.executor:
                    psi_batch = await self.executor.execute(psi)
                else:
                    psi_batch = [psi]

                ## 2. Handler Stage
                for p in psi_batch:
                    if asyncio.iscoroutinefunction(self.handler):
                        result = await self.handler(p)
                    else:
                        result = self.handler(p)

                    # 3. Actuator Stage (오타 수정: resutl -> result)
                    if result and self.actuator:
                        await self.actuator.actuate_psi(p)

                    # 4. Post-processing
                    if result and self.broadcaster:
                        self.broadcaster.broadcast(result)

                    if self.emitter:
                        await self.emitter.emit_psi(p)

                    self.processed += 1

            except Exception as e:
                # 에러 스택 추적을 위해 e를 그대로 출력하거나 로그 라이브러리 권장
                print(f"[Dispatcher:CriticalError] {type(e).__name__}: {e}")
            finally:
                self.queue.task_done()
                
            await asyncio.sleep(0)
        print("[Dispatcher] loop ended")

    async def stop(self):
        self.alive = False
        if self.task:
            await self.queue.put(None)
            await self.task

        print("[Dispatcher] Stopped")


    async def send(self, psi: PsiType):
        try:
            # put_nowait 대신 put을 사용하되 timeout을 주거나,
            # 현재 상태에서는 큐가 꽉 차면 대기(Backpressure)하도록 async로 기다리는 것이 좋습니다.
            await self.queue.put(psi) 
        except Exception as e:
            print(f"[Dispatcher] queue error: {e}")
            # 여기서 데이터를 Drop하지 말고, 센서가 속도를 늦추도록 에러를 전파하는 것이 좋습니다.
            raise e
