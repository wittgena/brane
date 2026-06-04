# swarm.trace.project.code
## @lineage: bound.trace.project.code
## @lineage: debugger.project.manager
## @lineage: debug.project.manager
## @lineage: gov.project.manager
## @lineage: gov.draft.project.manager
## @lineage: arch.proto.task.project.manager
## @lineage: arch.task.project.manager
## @lineage: foldbox.task.manager.project
import ast
import json
import argparse
import sys
import networkx as nx
from pathlib import Path
from collections import Counter
from typing import TypedDict, List, Dict, Any
from dataclasses import dataclass, asdict
from arch.proto.graph import MetaModel, NodeData, EdgeData, LoopEdgeData, GraphSchema
from watcher.plane.emitter import get_emitter
from phase.bind.resolver import resolve_path
from arch.topic.logic.transformer import LogicTransformer
from arch.topic.logic.analyzer import LogicAnalyzer

CODE_ROOT = resolve_path("code")
log = get_emitter("manager.project")

class ProjectManager:
    """@flow: filesystem → scan(Ψ_modules) → invoke(LogicAnalyzer) → Φ_schema → store(JSON)"""
    def __init__(self, root_path: str):
        self.repo_root = Path(root_path).resolve()
        self.analyzer = LogicAnalyzer()
        self.code_root = CODE_ROOT

    def run(self):
        if not self.repo_root.exists():
            log.info(f"[Error] Directory not found: {self.repo_root}")
            sys.exit(1)

        log.info(f"[Scanner] Indexing {self.repo_root.name}...")
        module_index = {
            ".".join(p.relative_to(self.repo_root).with_suffix("").parts): p 
            for p in self.repo_root.rglob("*.py")
        }

        log.info("[Linker] Building Topology Phase...")
        self.analyzer.build_structure(module_index, self.repo_root)
        
        result = self.analyzer.get_dissolve_schema(module_index, self.repo_root)
        self._write_json(result)
        return result

    def _write_json(self, data: GraphSchema):
        output_path = self.code_root / "node" / f"{self.repo_root.name}.link.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(asdict(data), f, indent=2, ensure_ascii=False)
        log.info(f"[Export] Dissolve topology saved to {output_path}")

def main():
    parser = argparse.ArgumentParser(description="Extract Topos & Dissolve Architecture Meta")
    parser.add_argument("--repo", required=True, help="Target python project repo")
    args = parser.parse_args()

    manager = ProjectManager(args.repo)
    schema = manager.run()

    log.info(f"  Total Modules: {schema.meta['total_modules']}")
    log.info(f"  Total Edges  : {schema.meta['total_dependencies']}")
    log.info(f"  Phase Stability Score: {schema.meta['phase_stability']} / 100")
    log.info(f"  Absorbable (Safe to Detach): {schema.meta['absorbable_count']} modules")
    log.info("\n[Distribution]")
    for k, v in sorted(schema.meta['phere_distribution'].items()):
        log.info(f"  - {k}: {v}")
    if schema.meta['cycles_detected'] > 0:
        log.info(f"\nWARNING: {schema.meta['cycles_detected']} cyclic resonances detected!")

if __name__ == "__main__":
    main()