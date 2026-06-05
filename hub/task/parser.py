# meta.debug.task.parser
from typing import List, Any
from nexus.hub.task.template import GraphSchema
from meta.xor.adapter.exam.example import Example
from watcher.plane.emitter import get_logger

log = get_logger("task.parser")

class TaskParser:
    """GraphSchema의 runtime log -> Example 포맷으로 변환"""
    def extract(self, node_id: str, schema: GraphSchema) -> List[Any]:
        trainset = []
        if not hasattr(schema, 'topos_edges') or not schema.topos_edges:
            log.warning(f"[Extract Traces] No edges found in schema for node: {node_id}")
            return trainset

        for edge in schema.topos_edges:
            if getattr(edge, 'source', None) != node_id:
                continue

            edge_data = getattr(edge, 'data', {})
            if not edge_data:
                continue

            context_signal = edge_data.get("context_signal", "")
            topology_map = edge_data.get("topology_map", "")
            rationale = edge_data.get("rationale", "")
            conflict_score = edge_data.get("conflict_score", 1.0)

            if not context_signal and not topology_map:
                continue

            example = Example(
                context_signal=context_signal,
                topology_map=topology_map,
                rationale=rationale,
                conflict_score=conflict_score
            )

            inputs = []
            if "context_signal" in edge_data:
                inputs.append("context_signal")
            if "topology_map" in edge_data:
                inputs.append("topology_map")
                
            example = example.with_inputs(*inputs)
            trainset.append(example)

        log.info(f"[Extract Traces] Extracted {len(trainset)} training examples for {node_id}")
        return trainset