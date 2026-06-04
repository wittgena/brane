# swarm.trace.project.bounder
## @lineage: bound.trace.project.bounder
## @lineage: debugger.project.bounder
## @lineage: debug.project.bounder
## @lineage: gov.project.bounder
## @lineage: gov.draft.project.bounder
## @lineage: arch.proto.task.bounder
## @lineage: arch.task.bounder
import os
import sys
import json
import argparse
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, Any, Optional, List, Union
from watcher.plane.emitter import get_logger
from phase.bind.resolver import resolve_path, get_invoker
from arch.proto.graph import EntryNode, RenderingData, _extract_rel_attr, EntryTemplate
from arch.proto.resonance import ResonanceGraph, ResonanceNode
from arch.topos.bind.manifold import ModelBinder
from arch.contract.registry.unified import cli_contract
from phase.runtime.cli.executor import dispatch_cli, execute_cli_task, CliTaskAdapter, parse_local

log = get_logger("task.bounder")

class SubgraphExtractor:
    @staticmethod
    def select(graph_data: dict, node: EntryNode) -> ResonanceGraph:
        full_nodes = {k: ResonanceNode(**v) for k, v in graph_data.get("nodes", {}).items()}
        
        entry_id = node.entry
        if entry_id not in full_nodes:
            log.warning(f"Entry point '{entry_id}' not found in the graph.")
            return ResonanceGraph(invariants=[], nodes={})

        selected_ids = {entry_id}
        current_level = {entry_id}
        
        for _ in range(node.depth):
            next_level = set()
            for n_id in current_level:
                for rel in full_nodes[n_id].relations:
                    rel_type = _extract_rel_attr(rel, "rel")
                    rel_target = _extract_rel_attr(rel, "target")
                    
                    if rel_type in node.valid_relations and rel_target in full_nodes:
                        next_level.add(rel_target)
            selected_ids.update(next_level)
            current_level = next_level

        sub_nodes = {}
        for n_id in selected_ids:
            node = full_nodes[n_id]
            filtered_rels = []
            for r in node.relations:
                r_type = _extract_rel_attr(r, "rel")
                r_target = _extract_rel_attr(r, "target")
                
                if r_target in selected_ids and r_type in node.valid_relations:
                    filtered_rels.append(r)
            
            sub_nodes[n_id] = ResonanceNode(
                id=node.id, intensity=node.intensity, is_invariant=node.is_invariant,
                boundaries=node.boundaries, support_manifold=node.support_manifold,
                relations=filtered_rels
            )

        return ResonanceGraph(invariants=[], nodes=sub_nodes)

class SurfaceFormatter:
    @staticmethod
    def _get_total_strength(node: ResonanceNode) -> int:
        """노드별 전체 관계 강도 합산"""
        return sum(_extract_rel_attr(r, "strength", 1) for r in node.relations)

    @classmethod
    def translate(cls, subgraph: ResonanceGraph, context: EntryNode) -> RenderingData:
        entry_point = context.entry

        ## Fragments (Nodes) Formatting
        fragments_blocks = []
        for f_id, node in subgraph.nodes.items():
            boundaries = json.dumps(node.boundaries, ensure_ascii=False)
            inv_mark = " *(Invariant)*" if node.is_invariant else ""
            prefix = "**[ENTRY]** " if f_id == entry_point else "- "
            fragments_blocks.append(f"{prefix}**`{f_id}`**{inv_mark} | Intensity: {node.intensity} | Boundaries: {boundaries}")
            
        fragments_str = "\n".join(fragments_blocks) if fragments_blocks else "- (No fragments)"

        ## Relations (Edges) Formatting - Top 7 x 7 필터링 적용
        relations_blocks = []
        
        ## 관계 강도 총합이 가장 높은 상위 7개 노드 추출
        top_source_nodes = sorted(
            subgraph.nodes.items(),
            key=lambda item: cls._get_total_strength(item[1]),
            reverse=True
        )[:7]

        ## 선택된 각 노드에 대해 상위 7개 관계만 추출
        for f_id, node in top_source_nodes:
            top_relations = sorted(
                node.relations,
                key=lambda r: _extract_rel_attr(r, "strength", 1),
                reverse=True
            )[:7]

            for rel in top_relations:
                rel_type = _extract_rel_attr(rel, "rel")
                rel_target = _extract_rel_attr(rel, "target")
                rel_strength = _extract_rel_attr(rel, "strength", 1)
                relations_blocks.append(f"- `{f_id}` --[{rel_type} (str: {rel_strength})]--> `{rel_target}`")
                
        relations_str = "\n".join(relations_blocks) if relations_blocks else "- (No relations within this scope)"
        return RenderingData(
            entry_point=entry_point,
            focus=context.focus,
            depth=str(context.depth),
            relations_list=", ".join(f"`{r}`" for r in context.relations),
            fragments=fragments_str,
            relations=relations_str
        )

class GraphProjector:
    def __init__(self, context: EntryNode):
        self.context = context

    def project(self, compiled_graph: dict) -> str:
        selector = SubgraphExtractor()
        subgraph = selector.select(compiled_graph, self.context)
        surface_data = SurfaceFormatter.translate(subgraph, self.context)
        return EntryTemplate.MARKDOWN.format(**asdict(surface_data))

class BoundRenderer:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def project_file(self, graph_file: Path, context: EntryNode) -> str:
        with open(graph_file, "r", encoding="utf-8") as f:
            compiled_graph = json.load(f)
            
        log.info(f"Initiating contextual projection for entry: {context.entry}")
        projector = GraphProjector(context)
        surface_content = projector.project(compiled_graph)

        out_name = f"{context.entry}.surface.md"
        output_path = self.output_dir / out_name
        output_path.write_text(surface_content, encoding="utf-8")

        log.info(f"[Φs] Contextual surface projected to {output_path}")
        return surface_content

class TaskBounder:
    def __init__(self, entry: str, target_repo: Optional[str] = None, depth: int = 2, relations: Optional[List[str]] = None):
        self.entry = entry
        self.target_dir = target_repo
        self.context = EntryNode(
            entry=entry,
            depth=depth,
            relations=relations or ["coupled"]
        )
        self.outdir = resolve_path("surface") 
        self.fixed_graph_path = resolve_path("xor") / "node" / "model.bound.json"

    def execute(self):
        if not self.fixed_graph_path.exists():
            log.info("[Auto-Bind] Graph topology missing. Orchestrating ModelBinder...")
            binder = ModelBinder()
            if self.target_dir:
                binder.model_root = resolve_path('model') / self.target_dir
                log.info(f"[Auto-Bind] Focusing bind scope to directory: {binder.model_root}")
            else:
                log.info("[Auto-Bind] Binding entire model manifold...")
            binder.execute()
            log.info("[Auto-Bind] Topology generation complete.")

        renderer = BoundRenderer(self.outdir)
        return renderer.project_file(self.fixed_graph_path, self.context)

def entry_task(args):
    parser = argparse.ArgumentParser(description="Contextual Boundary Projection (Φ′ + Context → Ψ → Φs)")
    parser.add_argument("--entry", required=True, help="Entry node ID (e.g., 특정 개념어나 클래스명)")
    parser.add_argument("--repo", default=None, help="Target model Repo (지정 안 하면 전체 model 스캔)")
    parser.add_argument("--relations", nargs='+', default=["coupled"], help="Relation types to follow")
    parsed_args = parser.parse_args(args)
    orchestrator = TaskBounder(
        entry=parsed_args.entry,
        target_repo=parsed_args.repo,
        depth=2,
        relations=parsed_args.relations,
    )
    return CliTaskAdapter(orchestrator.execute)

@cli_contract(name="task.bounder", recept=["lang.binder"])
def main():
    bound_args, remain = parse_local(sys.argv[1:])
    if bound_args.local:
        entry_task(remain).run()
    else:
        dispatch_cli("task.bounder", entry_task, __file__)

if __name__ == "__main__":
    main()