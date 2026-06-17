# phase.runtime.builder
from typing import Callable, Dict, Any
from arch.contract.context.assembler import ContextAssembler
from arch.contract.state.aggregator import KernelStateAggregator
from phase.bind.client.engine.local import LLMEngine
from phase.ator.reflect.worker import ReflectWorker
from phase.ator.reflect.coupler import ReflectCoupler

class CouplerBuilder:
    """
    @role: Theoria 계층의 내장 기관 조립 팩토리.
    """
    # Xor, Scanner 등 다양한 도구를 담을 레지스트리
    _providers: Dict[str, Any] = {}

    @classmethod
    def register_provider(cls, name: str, provider: Any):
        """
        ## @flow: Surgent/Ops 계층에서 도구를 주입하는 단일 연결점
        """
        cls._providers[name] = provider

    @classmethod
    def build(cls, interpreter, redis_client) -> ReflectCoupler:
        engine = LLMEngine()
        
        ## 빈 껍데기 Assembler 생성 (TypeError 해결)
        assembler = ContextAssembler()
        
        ## Builder가 쥐고 있던 도구들을 Assembler에 지연 바인딩(Injection)
        if hasattr(assembler, 'bind_provider'):
            for name, provider in cls._providers.items():
                assembler.bind_provider(name, provider)
                
        worker = ReflectWorker(engine, assembler)
        aggregator = KernelStateAggregator(interpreter, redis_client)
        
        return ReflectCoupler(aggregator, worker)