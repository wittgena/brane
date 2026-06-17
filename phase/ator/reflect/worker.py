# phase.ator.reflect.worker
import asyncio
from arch.contract.state.aggregator import InternalContext
from arch.contract.context.assembler import ContextAssembler
from phase.bind.client.engine.local import LLMEngine
from watcher.plane.emitter import get_emitter

log = get_emitter('reflect.worker')

class ReflectWorker:
    """@topos.worker: Cognitive Coupler로부터 InternalContext를 받아, 조립(Assemble)하고 판단(LLM)을 내리는 비동기 대뇌 피질"""
    def __init__(self, engine: LLMEngine, assembler: ContextAssembler):
        self.engine = engine
        self.assembler = assembler

    async def process(self, context: InternalContext):
        """@flow: InternalContext -> Assembler -> Messages -> Async LLM -> Action"""
        log.info(f"Worker initiated processing for Psi({context.event.symbol})")

        try:
            ## 컨텍스트 조립 (Assembly)
            query_text = f"Resolve intention for symbol: {context.event.symbol}"
            messages = self.assembler.assemble(
                query=query_text,
                anchor="당신은 meta.self의 핵심 인지 판단 코어입니다.",
                state=[f"Phase={context.state.phase}", f"Version={context.state.version}"],
                use_xor=True 
            )

            log.info("Projecting to local LLM Engine...")
            response_text = await asyncio.to_thread(
                self.engine.chat, 
                system_prompt=messages[0]['content'], # 단순화된 예시
                user_prompt=messages[-1]['content']
            )

            log.info(f"Cognitive resolution complete. Output length: {len(response_text)}")
            await self._handle_decision(context, response_text)
        except Exception as e:
            log.error(f"Cognitive process collapsed: {e}")
            ## 필요 시 자기 치유적 재귀 호출(Re-entry) 로직 발동 가능

    async def _handle_decision(self, context: InternalContext, response: str):
        """@action: LLM의 응답을 바탕으로 다음 액션(Actuator로 전송 등)을 수행"""
        pass