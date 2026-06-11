# channel.llm.response
## @lineage: gov.gateway.io.response
import warnings
from typing import ClassVar
from channel.switch.params import ResponsesAPIResponse
from channel.switch.params import ModelResponse
from pydantic import BaseModel, ConfigDict
from agent.call.tool.message import Message
from meta.watcher.tracker.conv.metrics import MetricsSnapshot

warnings.filterwarnings("ignore", message="Pydantic serializer warnings")

class LLMResponse(BaseModel):
    """Result of an LLM completion request"""
    message: Message
    metrics: MetricsSnapshot
    raw_response: ModelResponse | ResponsesAPIResponse
    model_config: ClassVar[ConfigDict] = ConfigDict(arbitrary_types_allowed=True)

    @property
    def id(self) -> str:
        """Get the response ID from the underlying LLM response"""
        return self.raw_response.id
