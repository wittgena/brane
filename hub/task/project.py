# hub.task.project
## @lineage: meta.debug.task.project
## @lineage: agent.manager.task.project
import json
import sys
import argparse
from pathlib import Path
from typing import Dict, Any, Optional, List, Type
from copy import deepcopy
from watcher.plane.emitter import get_emitter
from phase.bind.resolver import resolve_path
from arch.topic.logic.transformer import LogicTransformer
from arch.proto.context.signature import ProtoSignature
from arch.proto.schema.graph import GraphSchema, MetaModel, NodeData
from nexus.hub.task.optimizer import TaskOptimizer, TaskTopologyTranscription, DependencyConflictEvaluation

CODE_ROOT = resolve_path("code")
log = get_emitter("task.manager")

class TelemetryHydrator:
    """[텔레메트리 파서] GraphOrchestratorHandler의 런타임 추적 로그를 정형화"""
    def extract(self, log_path: Path) -> Dict[str, Any]:
        if not log_path.exists():
            return {"nodes": {}, "edges": []}
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            log.warning(f"[Telemetry] Failed to decode {log_path}. Returning empty trace.")
            return {"nodes": {}, "edges": []}

class TopologySynthesizer:
    """[위상 병합기] 정적 스캔 데이터 + 런타임 추적 데이터 병합"""
    def fuse(self, static_nodes: List[Dict], static_edges: List[Dict], telemetry: Dict) -> GraphSchema:
        fused_nodes = []
        for sn in static_nodes:
            node_id = sn['id']
            # GraphOrchestratorHandler가 기록한 node 메트릭 추출
            dyn_data = telemetry.get("nodes", {}).get(node_id, {})
            
            fused_nodes.append(NodeData(
                id=node_id,
                file_path=sn.get('file_path', ''),
                layer=sn.get('layer', 'tool'),  # StateProjector가 'opersig', 'projector' 등으로 변환할 힌트
                is_topos=sn.get('is_topos', False),
                degree=sn.get('degree', 0),
                betweenness=sn.get('betweenness', 0.0),
                signature_ref=dyn_data.get('signature_ref', f"{node_id}_Sig"),
                is_hydrated=bool(dyn_data),
                optimization_epoch=dyn_data.get('epoch', sn.get('optimization_epoch', 0)),
                # Telemetry의 실제 에러율 반영 (없으면 정적 기본값)
                failure_rate=dyn_data.get('failure_rate', 0.0)
            ))
        
        # [ALIGNMENT] StateProjector가 라우터를 생성할 수 있도록 Edge의 condition(aspect) 보존
        fused_edges = []
        for se in static_edges:
            fused_edges.append({
                "source": se.get("source"),
                "target": se.get("target"),
                "condition": se.get("condition")  # if present, triggers 'produces_aspect' rel
            })
        
        return GraphSchema(
            meta={}, 
            nodes=fused_nodes, 
            topos_edges=fused_edges, 
            loop_edges=[], 
            cycles=[], 
            invariants=[]
        )

class WorkflowStabilityEvaluator:
    """[워크플로우 평가기] 시스템 안정성 판별 및 병목(Bottleneck) 타겟 도출"""
    def evaluate(self, schema: GraphSchema) -> GraphSchema:
        if not schema.nodes:
            return schema

        total_failure = sum(getattr(n, 'failure_rate', getattr(n, 'failure_rate', 0.0)) for n in schema.nodes)
        node_count = len(schema.nodes)
        avg_failure = total_failure / node_count
        
        # 안정성 지표 계산 (실패율과 의존성 사이클 페널티 반영)
        stability_score = max(0.0, 100.0 - (avg_failure * 100) - (len(schema.cycles) * 10))
        
        # 병목 노드 식별: 실패율 30% 초과 & 잦은 실패
        bottleneck_nodes = [
            getattr(n, 'id', n['id']) for n in schema.nodes 
            if getattr(n, 'failure_rate', n.get('failure_rate', 0.0)) > 0.3
        ]
        
        schema.meta = MetaModel(
            total_modules=node_count,
            total_dependencies=len(schema.topos_edges),
            cycles_detected=len(schema.cycles),
            layer_distribution={},
            absorbable_count=0,
            phase_stability=round(stability_score, 2),
            entropy_delta=0.0,
            recompile_required=(stability_score < 70.0 or len(bottleneck_nodes) > 0),
            target_nodes_to_heal=bottleneck_nodes
        )
        return schema

class ProjectManager:
    """
    @flow: scan(Static) + hydrate(Dynamic) → fuse(Topology) → evaluate(Stability) → optimize → Project(Save)
    """
    def __init__(self, root_path: str):
        self.repo_root = Path(root_path).resolve()
        self.code_root = CODE_ROOT
        
        self.static_scanner = LogicTransformer()
        self.hydrator = TelemetryHydrator()
        self.synthesizer = TopologySynthesizer()
        self.evaluator = WorkflowStabilityEvaluator()
        self.optimizer = TaskOptimizer()

    def _resolve_signature(self, node_id: str) -> Type[ProtoSignature]:
        if "Transcriber" in node_id:
            return TaskTopologyTranscription
        elif "Evaluator" in node_id:
            return DependencyConflictEvaluation
        return TaskTopologyTranscription

    def run(self, telemetry_path: Optional[Path] = None) -> GraphSchema:
        if not self.repo_root.exists():
            log.error(f"[Error] Workspace root not found: {self.repo_root}")
            sys.exit(1)

        log.info(f"[Topology] Scanning Static Architecture: {self.repo_root.name}...")
        static_raw = self.static_scanner.parse_directory(self.repo_root)
        
        telemetry_data = {}
        if telemetry_path and telemetry_path.exists():
            log.info(f"[Telemetry] Hydrating runtime traces from {telemetry_path.name}")
            telemetry_data = self.hydrator.extract(telemetry_path)

        log.info("[Synthesis] Fusing structural graph and runtime telemetry...")
        fused_schema = self.synthesizer.fuse(
            static_nodes=static_raw.get("nodes", []), 
            static_edges=static_raw.get("edges", []), 
            telemetry=telemetry_data
        )

        final_schema = self.evaluator.evaluate(fused_schema)
        meta = final_schema.meta
        
        if meta.recompile_required:
            log.warning(f"⚠️ [Degradation] Stability critical: {meta.phase_stability}/100")
            bottlenecks = meta.target_nodes_to_heal
            log.info(f"🔄 [Optimization] Triggering dynamic recompilation for {len(bottlenecks)} bottleneck nodes...")
            
            # [ALIGNMENT] 안정성 롤백을 위한 스냅샷 저장
            pre_optimization_schema = deepcopy(final_schema)
            
            for node_id in bottlenecks:
                sig_class = self._resolve_signature(node_id)
                success = self.optimizer.optimize_task_node(node_id, sig_class, final_schema)
                
                if success:
                    for n in final_schema.nodes:
                        nid = getattr(n, 'id', n.get('id'))
                        if nid == node_id:
                            # 딕셔너리와 객체 접근 모두 지원하기 위한 처리
                            if hasattr(n, 'optimization_epoch'):
                                n.optimization_epoch += 1
                                n.failure_rate = 0.0 # 학습 후 에러율 초기화
                            else:
                                n['optimization_epoch'] += 1
                                n['failure_rate'] = 0.0
            
            # 재학습 후 안정성 재평가 (가상 시뮬레이션 또는 로직 평가)
            final_schema = self.evaluator.evaluate(final_schema)
            
            # [ALIGNMENT] 롤백 검증 로직 추가
            if final_schema.meta.phase_stability < pre_optimization_schema.meta.phase_stability:
                log.warning("🚨 [Rollback] Optimization resulted in lower stability. Rolling back to previous schema.")
                final_schema = pre_optimization_schema
            else:
                log.info(f"✨ [Restored] Post-optimization Stability: {final_schema.meta.phase_stability}/100")

        self._write_schema(final_schema)
        return final_schema

    def _write_schema(self, data: GraphSchema):
        output_path = self.code_root / "node" / f"{self.repo_root.name}.evo.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Pydantic Model일 경우 dict로 변환, 혹은 hasattr로 분기
        export_data = data.model_dump() if hasattr(data, 'model_dump') else (
            data.to_dict() if hasattr(data, 'to_dict') else data.__dict__
        )
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        log.info(f"[Projection] Evolved architecture state projected to {output_path}")

def main():
    parser = argparse.ArgumentParser(description="Task Architecture Orchestrator")
    parser.add_argument("--repo", required=True, help="Target system path")
    parser.add_argument("--telemetry", help="Path to runtime traces (JSON)")
    args = parser.parse_args()

    manager = ProjectManager(args.repo)
    schema = manager.run(Path(args.telemetry) if args.telemetry else None)

if __name__ == "__main__":
    main()