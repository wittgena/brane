# anchor.emit.code
## @lineage: meta.flow.emit.code
from __future__ import annotations
from typing import Any, Callable
from arch.xor.manifold.sign.signature import Signature, InputField, OutputField
from frame.scope.module.meta import Module
from meta.ops.predictor.code.gena import CodeGena
from meta.xor.adapter.exam.prediction import Prediction
from arch.proto.wrapper.code import CodeInterpreter
from watcher.plane.emitter import get_emitter

log = get_emitter("emit.code")

## Domain Signature: LLM의 인지적 흐름을 통제하는 명령형 지시문 기반 서명
class EmitCodeSignature(Signature):
    """
    당신은 위상 구조적 정합성을 갖춘 파이썬 코드를 생성하는 최고 수준의 시스템 아키텍트입니다.
    주어진 '목표(objective)'와 '컨텍스트(context)'를 철저히 분석하고, REPL 환경에서 검증 가능한 
    무상태(Stateless) 기반의 부수 효과(Side-effect) 없는 견고한 코드를 작성하여 방출하십시오.
    작업 과정에서 반드시 논리적 결함을 스스로 검증해야 합니다.
    """
    
    objective = InputField(desc="반드시 구현해야 할 핵심 알고리즘, 비즈니스 로직 또는 시스템 파이프라인의 명시적 목표입니다. 이 목표를 완벽하게 충족하는 코드를 설계하십시오.")
    context = InputField(desc="설계 시 엄격하게 준수해야 할 시스템 제약 조건, 메타데이터, 의존성 및 환경적 맥락입니다. 이 컨텍스트를 벗어나는 임의의 가정을 배제하십시오.")
    source_code = OutputField(
        desc="REPL 검증을 최종적으로 통과한 완전한 파이썬 소스 코드입니다. Markdown 포맷(```python 등)을 절대 포함하지 말고, 즉시 실행 가능한 순수 파이썬 텍스트만 방출하십시오."
    )
    explanation = OutputField(desc="작성된 코드의 아키텍처적 결정 사항, 상태 격리 방식, 그리고 위상 구조적 정합성에 대해 논리적이고 간결하게 설명하십시오.")


## Flow Module: 예측기(CodeGena)를 래핑하는 오케스트레이션 노드
class CodeEmitter(Module):
    """CodeGena 엔진을 응용하여 실제 코드 생성 및 방출(Emit) 파이프라인을 구동하는 Flow 노드"""
    def __init__(
        self,
        max_iterations: int = 15,
        max_llm_calls: int = 30,
        verbose: bool = False,
        tools: list[Callable] | None = None,
        interpreter: CodeInterpreter | None = None,
    ):
        super().__init__()
        self.generator = CodeGena(
            signature=EmitCodeSignature,
            max_iterations=max_iterations,
            max_llm_calls=max_llm_calls,
            verbose=verbose,
            tools=tools,
            interpreter=interpreter,
        )

    def forward(self, objective: str, context: dict[str, Any] | str) -> Prediction:
        if isinstance(context, dict):
            import json
            context_str = json.dumps(context, ensure_ascii=False, indent=2)
        else:
            context_str = str(context)

        result: Prediction = self.generator(objective=objective, context=context_str)
        return result

    async def aforward(self, objective: str, context: dict[str, Any] | str) -> Prediction:
        if isinstance(context, dict):
            import json
            context_str = json.dumps(context, ensure_ascii=False, indent=2)
        else:
            context_str = str(context)

        result: Prediction = await self.generator.acall(objective=objective, context=context_str)
        return result

if __name__ == "__main__":
    import asyncio
    import sys

    async def main():
        log.info("Initializing CodeEmitter...")
        
        # 1. CodeEmitter 인스턴스화
        # 테스트를 위해 verbose=True로 설정하여 내부 동작 로그를 확인합니다.
        emitter = CodeEmitter(
            max_iterations=5,
            max_llm_calls=10,
            verbose=True
        )

        # 2. 테스트용 Objective 및 Context 정의
        # 위상 구조적 정합성과 무상태(Stateless)를 검증하기 좋은 예제인 '순수 함수'를 요청합니다.
        test_objective = (
            "주어진 정수 N에 대해 피보나치 수열을 계산하여 리스트로 반환하는 최적화된 함수를 작성하십시오. "
            "메모이제이션(Memoization)을 내부 상태로 캡슐화하여 시간 복잡도를 O(N)으로 달성해야 합니다."
        )
        
        test_context = {
            "constraints": [
                "전역 변수(Global state)를 절대 사용하지 마십시오.",
                "부수 효과(Side-effect)가 없는 완전한 순수 함수(Pure function)로 설계하십시오.",
                "Python 3.9+ 표준 타입 힌트(Type hints)를 포함하십시오."
            ],
            "environment": "REPL 검증 환경"
        }

        log.info("Starting code emission process...")

        try:
            # 3. 비동기 추론 실행 (aforward)
            # 동기 환경이라면 prediction = emitter.forward(objective=test_objective, context=test_context) 사용
            prediction: Prediction = await emitter.aforward(
                objective=test_objective,
                context=test_context
            )

            # 4. 결과 출력
            # Signature에 정의된 OutputField(source_code, explanation)를 호출합니다.
            log.info("\n" + "="*60)
            log.info("🚀 [Generated Source Code]")
            log.info("="*60)
            log.info(getattr(prediction, 'source_code', 'No source code generated.'))

            log.info("\n" + "="*60)
            log.info("🧠 [Architectural Explanation]")
            log.info("="*60)
            log.info(getattr(prediction, 'explanation', 'No explanation generated.'))
            log.info("="*60 + "\n")

        except Exception as e:
            log.error(f"Error during code emission: {e}")
            sys.exit(1)

    # 비동기 이벤트 루프 실행
    asyncio.run(main())