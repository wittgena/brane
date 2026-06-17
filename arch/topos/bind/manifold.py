# arch.topos.bind.manifold
## @lineage: arch.topos.binder
## @lineage: arch.proto.task.binder
## @lineage: arch.task.binder
"""
@role: Class-based Boundary-driven Model Binder
@semantics:
- PosSensor: Detects ∂Φ
- ModelManifold: Maintains Φ nodes and edge coupling
- ModelBinder: Orchestrates the field formation
"""
import json
import sys
from pathlib import Path
from collections import defaultdict, Counter
from tqdm import tqdm
from watcher.plane.emitter import get_logger
from phase.bind.resolver import find_current_self, resolve_path
from arch.proto.schema.resonance import ResonanceGraph, ResonanceNode, NodeRelation
from arch.topic.pos.sensor import PosSensor

log = get_logger("model.binder")

class ModelManifold:
    """추출된 Φ 노드와 이들 간의 결합(Edge)을 관리하는 데이터 필드"""
    
    def __init__(self):
        self.node_intensity = Counter()
        self.node_support = defaultdict(set)
        self.node_boundaries = defaultdict(Counter)
        self.edge_field = Counter()

    def bind(self, seed, b_group, doc_path):
        """노드를 매니폴드에 결속"""
        self.node_intensity[seed] += 1
        self.node_support[seed].add(doc_path)
        self.node_boundaries[seed][b_group] += 1

    def couple(self, nodes):
        """노드들 간의 위상적 결합(Edge) 형성"""
        sorted_nodes = sorted(list(nodes))
        for i in range(len(sorted_nodes)):
            for j in range(i + 1, len(sorted_nodes)):
                edge = tuple(sorted([sorted_nodes[i], sorted_nodes[j]]))
                self.edge_field[edge] += 1

    def get_invariants(self, threshold=7):
        """다양한 경계 속성을 가진 불변 노드 식별"""
        return [n for n, b_counts in self.node_boundaries.items() if len(b_counts) >= threshold]

class ModelBinder:
    """모델을 순회하며 위상 필드를 구축하고 투영(Projection)을 생성하는 오케스트레이터"""

    def __init__(self):
        self.sensor = PosSensor()
        self.manifold = ModelManifold()
        self.model_root = resolve_path('model')
        self.output_path = resolve_path("xor") / "node" / "model.bound.json"

    def execute(self):
        log.info(f"Binding Model Field from: {self.model_root}")
        
        files = list(self.model_root.rglob("*.md"))
        for path in tqdm(files, desc="Processing Documents"):
            try:
                text = path.read_text(encoding="utf-8")
                candidates = self.sensor.sense(text)
                
                doc_nodes = set()
                for seed, b_group in candidates:
                    self.manifold.bind(seed, b_group, str(path))
                    doc_nodes.add(seed)
                
                self.manifold.couple(doc_nodes)
            except Exception as e:
                log.error(f"Error in {path.name}: {e}")

        self._project()

    def _project(self, top_k=100):
        invariants = self.manifold.get_invariants()
        top_seeds = [n for n, _ in self.manifold.node_intensity.most_common(top_k)]
        
        ## 모델 클래스 기반 노드 초기화
        nodes_dict = {}
        for seed in top_seeds:
            nodes_dict[seed] = ResonanceNode(
                id=seed,
                intensity=self.manifold.node_intensity[seed],
                is_invariant=(seed in invariants),
                boundaries=dict(self.manifold.node_boundaries[seed]),
                support_manifold=sorted(list(self.manifold.node_support[seed]))[:3]
            )

        ## 엣지 데이터를 모델 클래스로 주입
        for (u, v), weight in self.manifold.edge_field.items():
            if weight >= 2 and u in top_seeds and v in top_seeds:
                nodes_dict[u].relations.append(NodeRelation(target=v, strength=weight))
                nodes_dict[v].relations.append(NodeRelation(target=u, strength=weight))

        ## 최종 그래프 객체 생성
        topos_graph = ResonanceGraph(
            invariants=invariants,
            nodes=nodes_dict
        )

        ## JSON 투영 (to_dict 활용)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_path, "w", encoding="utf-8") as f:
            json.dump(topos_graph.to_dict(), f, ensure_ascii=False, indent=2)
            
        log.info(f"Model Manifold Projection completed: {self.output_path}")

if __name__ == "__main__":
    binder = ModelBinder()
    binder.execute()