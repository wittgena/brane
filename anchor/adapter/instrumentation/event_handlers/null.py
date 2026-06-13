# anchor.adapter.instrumentation.event_handlers.null
## @lineage: bound.adapter.instrumentation.event_handlers.null
## @lineage: bridge.llama.core.instrumentation.event_handlers.null
from typing import Any
from anchor.adapter.instrumentation.base.event import BaseEvent
from anchor.adapter.instrumentation.event_handlers.base import BaseEventHandler

class NullEventHandler(BaseEventHandler):
    @classmethod
    def class_name(cls) -> str:
        """Class name."""
        return "NullEventHandler"

    def handle(self, event: BaseEvent, **kwargs: Any) -> Any:
        """Handle logic - null handler does nothing."""
        return
