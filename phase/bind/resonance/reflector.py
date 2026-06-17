# phase.bind.resonance.reflector
## @lineage: phase.resonance.reflector
## @lineage: swarm.resonance.reflector
import ast
import asyncio
import inspect
from pathlib import Path
from typing import Any, Dict
from phase.ator.runtime import AtorRuntime
from arch.proto.phase.flow import PhaseFlow, FlowState, Align, Resonance, Transduction
from arch.contract.registry.unified import contract
from watcher.plane.emitter import get_logger

log = get_logger('ator.reflector')

@contract.ator("ator.reflector")
class AtorReflector(Transduction):
    def transduce(self, flow: PhaseFlow, ator_node: Any) -> PhaseFlow:
        # 1. 포장지(raw_input) 내부로 진입
        raw = flow.payload.get("raw_input", {})
        file_path = raw.get("source_path")
        task_data = raw.get("task")

        if not file_path:
            raise KeyError("Inversion Point (source_path) missing in raw_input")

        log.info(f"  [Reflect] Inverting from source: {file_path}")

        # 2. 소스 분석 (DNA 추출)
        with open(file_path, "r", encoding="utf-8") as f:
            source = f.read()

        tree = ast.parse(source)
        topology = self._extract_phi(tree)

        # 3. 중첩(Folding)의 완성
        # 추출된 topology와 기존 task 데이터를 결합하여 신호를 물질화 필드로 보냄
        materialization_seed = {
            "topology": topology,
            "task": task_data,
            "meta_context": flow.payload # 전체 맥락 유지
        }

        return self._close(materialization_seed, flow, ator_node)

    def _extract_phi(self, tree: ast.AST) -> Dict[str, Any]:
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "PHI":
                        return ast.literal_eval(node.value)
        raise ValueError("PHI not found")

@contract.ator("runtime.aligner")
class RuntimeAligner(Align):
    """@flow: Φ(runtime_nodes) → Φ(bound runtime)"""

    def align(self, flow: PhaseFlow, spec: Dict[str, Any]) -> Dict[str, Any]:
        runtime_nodes = flow.payload

        if not isinstance(runtime_nodes, dict) or not runtime_nodes:
            return {
                "status": "error",
                "payload": flow.payload,
                "state": {"alignment_status": "failed", "reason": "invalid_nodes"}
            }

        try:
            # context에서 runtime_node 가져오는 구조가 아니라
            # node 내부에서 접근해야 정합
            runtime_node = getattr(self, "base_node", None)
            if runtime_node is None:
                return {
                    "status": "error",
                    "payload": flow.payload,
                    "state": {"alignment_status": "failed", "reason": "missing_runtime"}
                }

            entry = next(iter(runtime_nodes))
            flow_controller = AtorRuntime(
                entry=entry,
                nodes=runtime_nodes,
                runtime_node=runtime_node
            )
            flow_controller.attach()
            return {
                "status": "stable",
                "payload": {
                    "entry": entry,
                    "node_count": len(runtime_nodes)
                },
                "state": {
                    "alignment_status": "success"
                }
            }
        except Exception as e:
            return {
                "status": "fractured",
                "payload": flow.payload,
                "state": {
                    "alignment_status": "failed",
                    "error": str(e)
                }
            }
