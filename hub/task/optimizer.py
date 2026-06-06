# hub.task.optimizer
## @lineage: meta.debug.task.optimizer
## @lineage: agent.manager.task.optimizer
import asyncio
from typing import List, Any, Type, Optional
from arch.proto.context.signature import ProtoSignature, In, Out
from gov.scope.thch import ThCh, _compile_to_sign
from gov.scope.manager import managed_scope
from watcher.plane.emitter import get_logger
from arch.proto.schema.graph import GraphSchema
from nexus.hub.task.parser import TaskParser
from gov.frame.rule.fitter import RuleFitter

log = get_logger("task.optimizer")

class TaskTopologyTranscription(ProtoSignature):
    """[Phase 1: Projection] 비정형 요구사항을 선언적 Task 위상 구조로 변환합니다."""
    context_signal: str = In(desc="비정형적 작업 요구사항 또는 시스템 에러 로그")
    topology_map: str = Out(desc="노드(Task)와 엣지(Dependency)로 구성된 선언적 위상 구조 JSON")
    rationale: str = Out(desc="해당 작업 파이프라인을 구성한 논리적 근거 (Rationale)")

class DependencyConflictEvaluation(ProtoSignature):
    """[Phase 2: Judgment] 생성된 Task 위상 내의 의존성 충돌(Deadlock, Cycle) 위험을 평가합니다."""
    topology_map: str = In()
    conflict_score: float = Out(desc="0.0(안전) ~ 1.0(교착상태/충돌) 사이의 충돌 예상 지표")
    resolution_guide: str = Out(desc="의존성 충돌 해소를 위한 Task 재배치 가이드")

class TaskOptimizer:
    """ProjectManager가 식별한 병목 에이전트(Node)의 과거 실행 기록(Traces)을 바탕으로 에이전트의 프롬프트와 가중치를 재컴파"""
    def __init__(
        self, 
        state_path: str = "workspace/state/task_routing_weights.json",
        trace_extractor: Optional[Any] = None
    ):
        self.state_path = state_path
        self.trace_extractor = trace_extractor or TaskParser()

    def optimize_task_node(self, node_id: str, signature_class: Type[ProtoSignature], schema: GraphSchema):
        log.info(f"[Optimizer] Initiating dynamic compilation for Task Node: {node_id}")
        trainset = self.trace_extractor.extract(node_id, schema)
        if not trainset:
            log.warning(f"[Optimizer] Insufficient runtime traces for {node_id}. Compilation aborted.")
            return False

        ## 타겟 시그니처에 맞춘 동적 파사드(Dynamic Module) 컴파일
        compiled_module = self._compile_dynamic_module(signature_class, trainset)
        
        ## 최적화된 상태(Weights)를 저장
        save_key = f"{node_id}_optimized"
        compiled_module.save(self.state_path, prefix=save_key)
        
        log.info(f"[Optimizer] Success. {node_id} prompt weights updated and saved to '{save_key}'.")
        return True

    def _compile_dynamic_module(self, signature_class: Type[ProtoSignature], trainset: List[Any]):
        from gov.scope.module.meta import Module
        from meta.ops.predictor.cot import ChainOfThought
        class DynamicTaskModule(Module):
            def __init__(self):
                super().__init__()
                self.engine = ChainOfThought(_compile_to_sign(signature_class))
            def forward(self, **kwargs):
                return self.engine(**kwargs)

        def workflow_stability_metric(gold, pred, trace=None):
            conflict = getattr(pred, "conflict_score", 0.0) if hasattr(pred, 'conflict_score') else 0.0
            return 1.0 - float(conflict)

        optimizer = RuleFitter(metric=workflow_stability_metric, max_errors=3)
        return optimizer.compile(DynamicTaskModule(), trainset=trainset, num_trials=10)

class RuntimeTaskAligner:
    """실제 런타임에 작업을 위상 구조로 파싱하고 평가하는 가벼운 ThCh 래퍼"""
    def __init__(self, state_path: str = "workspace/state/task_routing_weights.json"):
        self.transcriber = ThCh(TaskTopologyTranscription, state_path=state_path, state_key="transcriber_optimized")
        self.evaluator = ThCh(DependencyConflictEvaluation, state_path=state_path, state_key="evaluator_optimized")

    async def forward(self, context_signal: str, model_name: str = "local-gemma-3") -> dict:
        with managed_scope(use_dphi=True, use_thch=True, dphi_model=model_name):
            return await self._process_flow(context_signal)

    async def _process_flow(self, context_signal: str) -> dict:
        transcription = self.transcriber(context_signal=context_signal)
        evaluation = self.evaluator(topology_map=transcription.topology_map)
        conflict_score = float(evaluation.conflict_score) if hasattr(evaluation, 'conflict_score') else 1.0
        if conflict_score > 0.7:
            log.error(f"[Task Execution] Dependency Conflict Detected (Score: {conflict_score}).")
            raise RuntimeError(f"Workflow Conflict Threshold Exceeded: {conflict_score}")

        return {
            "topology": transcription.topology_map,
            "conflict_score": conflict_score,
            "rationale": transcription.rationale
        }