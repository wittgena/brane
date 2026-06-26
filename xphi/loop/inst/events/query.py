# xphi.loop.inst.events.query
## @lineage: bound.adapter.llama.instrumentation.events.query
## @lineage: bound.adapter.instrumentation.events.query
## @lineage: anchor.adapter.instrumentation.events.query
from xphi.loop.inst.events.base import BaseEvent
from xphi.adapter.llama.base.response.schema import RESPONSE_TYPE
from xphi.adapter.llama.schema import QueryType


class QueryStartEvent(BaseEvent):
    """
    QueryStartEvent.

    Args:
        query (QueryType): Query as a string or query bundle.

    """

    query: QueryType

    @classmethod
    def class_name(cls) -> str:
        """Class name."""
        return "QueryStartEvent"


class QueryEndEvent(BaseEvent):
    """
    QueryEndEvent.

    Args:
        query (QueryType): Query as a string or query bundle.
        response (RESPONSE_TYPE): Response.

    """

    query: QueryType
    response: RESPONSE_TYPE

    @classmethod
    def class_name(cls) -> str:
        """Class name."""
        return "QueryEndEvent"
