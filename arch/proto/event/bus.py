# arch.proto.event.bus
## @lineage: phase.bind.event.bus
## @lineage: arch.event.bus
## @lineage: arch.contract.event.bus
## @lineage: arch.model.event.bus
import asyncio
from typing import Dict, Any, List, Optional
from arch.proto.event.psi import PsiEvent
from arch.contract.interface import IPhaseAtor, IPhaseField, IEventBus
from watcher.plane.emitter import get_emitter

class AsyncEventBus(IEventBus):
    """@desc: Actor isolation + bounded fan-out"""
    def __init__(self):
        self.actors: List[IPhaseAtor] = []
        self.field: Optional[IPhaseField] = None
        self.log = get_emitter("system.bus", phase="NETWORK")

    def bind_field(self, field: IPhaseField):
        self.field = field

    def subscribe(self, actor: IPhaseAtor):
        self.actors.append(actor)

    async def publish(self, event: PsiEvent):
        # fan-out을 gather로 제한 (폭주 방지)
        tasks = [
            self._safe_react(actor, event)
            for actor in self.actors
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _safe_react(self, ator: IPhaseAtor, event: PsiEvent):
        try:
            await ator.react(event, self.field, self)
        except Exception as e:
            self.log.error(f"[FAIL] {ator.actor_id} on {event.event_type}: {e}")
