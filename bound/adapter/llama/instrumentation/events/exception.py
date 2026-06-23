# bound.adapter.llama.instrumentation.events.exception
## @lineage: bound.adapter.instrumentation.events.exception
## @lineage: anchor.adapter.instrumentation.events.exception
from bound.adapter.llama.instrumentation.events import BaseEvent


class ExceptionEvent(BaseEvent):
    """
    ExceptionEvent.

    Args:
        exception (BaseException): exception.

    """

    exception: BaseException

    @classmethod
    def class_name(cls) -> str:
        """Class name."""
        return "ExceptionEvent"
