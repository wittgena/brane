# phase.ator.reflect.coupler
import asyncio
from typing import Optional

from arch.proto.event.psi import PsiEvent, PsiCarrier
from arch.contract.state.aggregator import KernelStateAggregator, InternalContext
from phase.runtime.interpreter import PhaseJudgment
from phase.ator.reflect.worker import ReflectWorker
from watcher.plane.emitter import get_emitter

class ReflectCoupler:
    """
    @topos.fiber_bundle: 척수(Dispatcher)와 대뇌(LLM Worker)를 잇는 비동기 위상 교량
    @flow: PhaseJudgment(Sync) -> Queue -> State Aggregation(Async) -> Worker Projection
    """
    def __init__(self, aggregator: KernelStateAggregator, worker: ReflectWorker):
        self.aggregator = aggregator
        self.worker = worker
        self.tension_queue = asyncio.Queue() # 압력을 흡수하는 버퍼 공간
        self.log = get_emitter("node.coupler", phase="BRIDGE")
        self.running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """교량 점화 (NodeRuntime의 start 시점에 함께 호출됨)"""
        self.running = True
        self._task = asyncio.create_task(self._consume_loop(), name="ReflectCoupler")
        self.log.info("Reflect Coupler bound and listening.")

    async def stop(self):
        self.running = False
        await self.tension_queue.put(None) # Poison pill
        if self._task:
            await self._task

    def ingest(self, psi: PsiCarrier, judgment: PhaseJudgment):
        """
        @boundary.entry: Dispatcher(Sync)가 호출하는 접점. 
        판단 결과를 큐에 밀어넣고 즉시 리턴하여 루프의 병목을 막는다.
        """
        if judgment.is_resonance:
            # 큐에 적재하여 비동기 워커가 소화할 수 있도록 위임
            self.tension_queue.put_nowait((psi, judgment))
            self.log.trace(f"Psi({psi.symbol}) crossed the boundary. Tension queued.")
        else:
            self.log.trace(f"Psi({psi.symbol}) dropped by interference.")

    async def _consume_loop(self):
        """
        @boundary.exit: Queue에서 이벤트를 꺼내 심층 인지(LLM)로 투사하는 비동기 루프
        """
        while self.running:
            try:
                payload = await self.tension_queue.get()
                if payload is None:
                    break # Shutdown signal
                
                psi, judgment = payload
                
                # 1. 잃어버린 고리 복원: 비동기 런타임 상태 응축 (Scan Redis)
                self.log.info(f"Aggregating internal state for Psi({psi.symbol})...")
                internal_ctx: InternalContext = await self.aggregator.build_context(psi)
                
                # 2. 대뇌(LLM Worker)로 투사
                self.log.info("Projecting context to Cognitive Worker...")
                await self.worker.process(internal_ctx)
                
                self.tension_queue.task_done()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.log.error(f"Coupler processing error: {e}")