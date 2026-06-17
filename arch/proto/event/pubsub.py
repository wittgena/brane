# arch.proto.event.pubsub
## @lineage: arch.proto.pubsub
import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TypeVar
from arch.proto.event.next import next_id
from watcher.plane.emitter import get_emitter

logger = get_emitter(__name__)

T = TypeVar("T")
ToposId = str

class Subscriber[T](ABC):
    @abstractmethod
    async def __call__(self, event: T):
        """Invoke this subscriber"""

    async def close(self):
        """Clean up this subscriber"""


@dataclass
class PubSub[T]:
    _subscribers: dict[ToposId, Subscriber[T]] = field(default_factory=dict)

    def subscribe(self, subscriber: Subscriber[T]) -> ToposId:
        subscriber_id = next_id()
        self._subscribers[subscriber_id] = subscriber
        logger.debug(f"Subscribed subscriber with ID: {subscriber_id}")
        return subscriber_id

    def unsubscribe(self, subscriber_id: ToposId) -> bool:
        if subscriber_id in self._subscribers:
            del self._subscribers[subscriber_id]
            logger.debug(f"Unsubscribed subscriber with ID: {subscriber_id}")
            return True
        else:
            logger.warning(
                f"Attempted to unsubscribe unknown subscriber ID: {subscriber_id}"
            )
            return False

    async def __call__(self, event: T) -> None:
        for subscriber_id, subscriber in list(self._subscribers.items()):
            try:
                await subscriber(event)
            except Exception as e:
                logger.error(f"Error in subscriber {subscriber_id}: {e}", exc_info=True)

    async def close(self):
        await asyncio.gather(
            *[subscriber.close() for subscriber in self._subscribers.values()]
        )
        self._subscribers.clear()
