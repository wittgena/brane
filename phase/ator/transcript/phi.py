# phase.ator.transcript.phi
## @lineage: phase.hub.ator.transcript.phi
## @lineage: hub.ator.transcript.phi
## @lineage: xe.ator.transcript.phi
## @lineage: xphi.transcript.phi
## @lineage: cognitive.xphi.transcript.phi
## @lineage: meta.transcript.phi
## @lineage: cognitive.transcript.phi
import asyncio
import json
import inspect
import ast
import re
import yaml
from abc import abstractmethod
from typing import Any, Dict, List, Tuple
from watcher.plane.emitter import get_logger
from arch.proto.phase.flow import PhaseFlow, FlowState, Transduction
from arch.contract.registry.unified import contract, registry
from arch.xor.block.parser.md import MdAstParser
from arch.xor.block.extractor import BlockExtractor

log = get_logger("transcript.phi")

class TranscriptBase(Transduction):
    """@flow: Ψ → Φ transformer (transcription + translation boundary)"""
    def __init__(self, base_node: Any = None):
        self.base_node = base_node
        self.manifold = getattr(base_node, "local_manifold", {})

        self.role = "transcript.base"
        self.node_context = {
            "instruction": "System Materialization Kernel",
            "role": self.role
        }

    def transduce(self, flow: PhaseFlow, ator_node: Any) -> PhaseFlow:
        """@phase: Projection (Ψ_reflect)"""
        file_path = flow.payload
        log.info(f"  [Projection] Reflecting source: {file_path}")
        projected_topology = self._reflect_source(file_path)
        return self._close(projected_topology, flow, ator_node)

    def _execute_transformation(self, topology: Dict[str, Any], instruction: str) -> Dict[str, Any]:
        """Translation (Ψ → Φ_materialized)"""
        log.info("    [Kernel] Materializing Topology into Node Instances")
        runtime_nodes = {}
        
        ## 위상 구조 호환성 계층 (Compatibility Layer)
        # 캡슐화된 구조({"entry": ..., "nodes": {...}})라면 nodes만 추출하고, 
        # 레거시 구조라면 그대로 사용합니다.
        nodes_topology = topology.get("nodes", topology) if isinstance(topology, dict) else topology

        ## 추출된 노드 맵을 순회
        for node_id, config in nodes_topology.items():
            # (안전장치) 혹시 모를 메타데이터 키가 섞여 있다면 패스
            if not isinstance(config, dict) or "type" not in config:
                continue
                
            node_type = config["type"]
            spec = config["spec"]
            
            if node_type not in self.manifold:
                raise ValueError(f"Unknown node type '{node_type}'")
            
            NodeClass = self.manifold[node_type].node_class
            node_instance = NodeClass(spec)
            
            target_operator = spec.get("operator")
            if target_operator:
                operator_instance = registry.create_component("ator", {"type": target_operator})
                node_instance.bound_operator = operator_instance

            runtime_nodes[node_id] = node_instance
            
        return runtime_nodes

    @abstractmethod
    def _reflect_source(self, file_path: str) -> Dict[str, Any]:
        """소스를 해석하여 Dict(Topology)를 반환하는 메서드 (Subclass must implement)"""
        pass

@contract.ator("transcript.phi")
class TranscriptPhi(TranscriptBase):
    """@flow: Ψ → Φ transformer (transcription + translation boundary)"""
    def __init__(self, base_node: Any):
        super().__init__(base_node)
        self.role = "transcript.phi"

    def _reflect_source(self, file_path: str) -> Dict[str, Any]:
        with open(file_path, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == 'XPHI':
                        return ast.literal_eval(node.value)
        raise ValueError(f"XPHI not found in {file_path}")