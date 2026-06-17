# phase.bind.client.engine.base
## @lineage: phase.bound.client.engine.base
## @lineage: phase.reflect.client.engine.base
from abc import ABC, abstractmethod
from arch.proto.schema.resonance import BridgeEvent

class BaseEngine(ABC):
    @abstractmethod
    def ask(self, prompt: str, callback: callable) -> str:
        """엔진에 질문을 던지고 스트리밍 이벤트를 콜백으로 전달"""
        pass