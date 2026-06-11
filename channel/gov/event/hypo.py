# channel.gov.event.hypo
## @lineage: gov.gateway.event.hypo
import asyncio
from dataclasses import dataclass, field
from channel.gov.event.conversation import EventService
from arch.proto.event.pubsub import Subscriber
from agent.loop.event.base import Event
from agent.loop.event.llm.message import MessageEvent
from gov.frame.hypo.generator import HypoGenerator
from watcher.plane.emitter import get_logger

logger = get_logger("event.hypo")

@dataclass
class HypoSubscriber(Subscriber):
    service: EventService
    generator: HypoGenerator = field(default_factory=HypoGenerator)
    event_buffer: list[Event] = field(default_factory=list)
    trigger_threshold: int = 3 # 3개의 메시지가 쌓일 때마다 가설 생성

    async def __call__(self, event: Event) -> None:
        ## User나 Agent의 메시지 이벤트만 버퍼에 수집
        if not isinstance(event, MessageEvent):
            return
            
        self.event_buffer.append(event)
        
        ## 임계치에 도달하면 가설 생성 및 검증 파이프라인 백그라운드 실행
        if len(self.event_buffer) >= self.trigger_threshold:
            events_to_process = [e.model_dump() for e in self.event_buffer]
            self.event_buffer.clear()
            
            asyncio.create_task(self._generate_and_organize(events_to_process))

    async def _generate_and_organize(self, events: list[dict]) -> None:
        try:
            conversation_id = self.service.stored.id.hex
            ## HypoGenerator를 통한 가설 생성
            loop = asyncio.get_running_loop()
            hypotheses = await loop.run_in_executor(
                None, 
                self.generator.generate_from_events, 
                conversation_id, 
                events
            )
            ## HypoOrganizer(Verifier + Crystallizer)로 데이터를 넘겨 검증 및 DB 저장 수행
            ## organizer.process_dynamic_hypotheses(hypotheses)
        except Exception as e:
            logger.warning(f"Dynamic hypothesis generation failed for conversation {conversation_id}: {e}")