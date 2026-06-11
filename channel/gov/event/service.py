# channel.gov.event.service
## @lineage: gov.gateway.event.service
## @lineage: gov.gateway.service.event
## @lineage: gov.gateway.event
## @lineage: gov.bridge.event
## @lineage: gov.io.bridge.event
## @lineage: bound.io.bridge.event
import asyncio
from typing import Any
from agent.loop.conv.state import ConversationExecutionStatus
from agent.loop.event.llm.action import ActionEvent
from arch.proto.event.bus import AsyncEventBus
from arch.contract.interface import IPhaseAtor, IPhaseField
from arch.proto.event.psi import PsiEvent, PsiCarrier, CarrierType, PhaseField
from arch.proto.event.network import EventTransductor
from arch.proto.event.next import next_id, next_phase_id
from watcher.plane.emitter import get_emitter

log = get_emitter("bridge.event")

class AgentEventTransductor(EventTransductor[Any]):
    """bound.agent의 이벤트를 기저 시스템의 PsiEvent로 변환 (Transduction)"""
    
    def transduce(self, agent_event: Any, conversation_state: Any) -> PsiEvent:
        # Agent의 특정 상태나 이벤트 종류에 따라 태그 분류
        tag = "execute"
        carrier_type = CarrierType.LOCAL
        
        # 위험 감지 및 승인 대기 상태일 경우 (고위험/긴장 상태)
        if isinstance(agent_event, ActionEvent) and \
           conversation_state.execution_status == ConversationExecutionStatus.WAITING_FOR_CONFIRMATION:
            tag = "await_confirmation"
            carrier_type = CarrierType.MODULATORY # 외부 개입(지연)이 필요한 공명
            
        # PsiCarrier 조립
        carrier = PsiCarrier(
            kind=type(agent_event).__name__,
            tag=tag,
            payload=agent_event,
            carrier_type=carrier_type,
            target_field=PhaseField.COHERENT
        )
        
        # 차분 위상 신호 생성 (예: 긴장도 증가)
        pressure_val = 10 if tag == "await_confirmation" else 0
        p_id = next_phase_id(topo=1, press=pressure_val)
        
        return PsiEvent(
            event_id=next_id(),
            parent_id=None,
            source_id="agent.step",
            scope="RUNTIME",
            tick=int(asyncio.get_event_loop().time()),
            carrier=carrier,
            phase_id=p_id
        )

class NotificationAtor(IPhaseAtor):
    """PsiEvent를 구독하여 외부 channel과 통신하는 독립 액터"""
    
    @property
    def actor_id(self) -> str:
        return "ator.slack_notifier"
        
    async def react(self, event: PsiEvent, field: IPhaseField, bus: AsyncEventBus):
        # Transductor가 태깅한 symbol(kind:tag)을 기반으로 라우팅
        if event.tag == "await_confirmation":
            agent_event = event.payload  # 원래의 ActionEvent 복원
            tool_name = getattr(agent_event, 'tool_name', 'Unknown')
            risk = getattr(agent_event, 'security_risk', 'High')
            
            # 외부 API 비동기 호출 (실제 로직 구현부)
            print(f"[Slack Alert] ⚠️ 승인 대기 중! Tool: {tool_name}, Risk: {risk}")
            print(f"[Slack Alert] Event ID: {event.event_id}, Phase ID: {hex(event.phase_id)}")

async def run_agent_with_arch_bus(agent, conversation):
    bus = AsyncEventBus()
    
    # 여러 액터(로거, 알림, 메트릭 등) 구독 설정
    bus.subscribe(NotificationAtor())
    # bus.subscribe(TelemetryAtor()) 
    
    transductor = AgentEventTransductor()

    def sync_on_event_bridge(agent_event):
        """
        bound.agent의 동기적(sync) on_event 콜백을 
        비동기(async) Event Bus로 태워보내는 어댑터 함수
        """
        # 1. Transduce: Agent Event -> PsiEvent
        psi_event = transductor.transduce(agent_event, conversation.state)
        
        # 2. Publish (이벤트 루프에 태스크 던지기 - 에이전트 블로킹 방지)
        asyncio.create_task(bus.publish(psi_event))

    # 에이전트는 기저 시스템(Bus, Transductor 등)을 전혀 모른 채 실행됨
    agent.step(conversation, on_event=sync_on_event_bridge)