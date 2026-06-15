# bound.adapter.instrumentation.base.handler
## @lineage: anchor.adapter.instrumentation.base.handler
## @lineage: bridge.llama.core.instrumentation.base.handler
from abc import ABC, abstractmethod


class BaseInstrumentationHandler(ABC):
    @classmethod
    @abstractmethod
    def init(cls) -> None:
        """Initialize the instrumentation handler."""
