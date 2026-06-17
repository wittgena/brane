# arch.topos.gov.node.discovery
## @lineage: gov.state.node.discovery
## @lineage: gov.state.system.node.discovery
## @lineage: gov.repo.node.discovery
"""
@topos.role: Φ constructor (global topology discovery)
@desc: A pure logical scanner decoupled from physical implementations (e.g., Git).
       Discovers nodes based on an injected predicate.
"""
from pathlib import Path
from typing import List, Callable
from watcher.plane.emitter import get_emitter

log = get_emitter("node.discovery", mode="SLIM")

class NodeDiscovery:
    def __init__(self, root_path: Path, is_node_fn: Callable[[Path], bool]):
        """
        :param root_path: 탐색을 시작할 기준 위상(Root Topology)
        :param is_node_fn: 특정 경로가 노드인지 판별하는 주입된 함수 (IoC)
        """
        self.root = root_path
        self.is_node = is_node_fn
        log.info(f"[NodeDiscovery] root_path: {self.root}")

    def scan(self, depth: int = 2) -> List[Path]:
        """주어진 깊이만큼 하위 디렉토리를 순회하며 노드를 추출"""
        found_nodes: List[Path] = []
        log.info(f"scan start: {self.root} (Max Depth: {depth})")

        for entry in self.root.iterdir():
            if not (entry.is_dir() or entry.is_symlink()): 
                continue

            # 주입된 판별기를 통해 노드 여부 확인
            if self.is_node(entry):
                found_nodes.append(entry)

            # 지정된 깊이까지 하위 순회
            if depth > 1:
                for sub in entry.iterdir():
                    if (sub.is_dir() or sub.is_symlink()) and self.is_node(sub):
                        found_nodes.append(sub)

        log.info(f"total nodes discovered: {len(found_nodes)}")
        for node_path in found_nodes:
            log.info(f"node.path: {node_path}")
            
        return found_nodes