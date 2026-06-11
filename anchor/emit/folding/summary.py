# anchor.emit.folding.summary
## @lineage: meta.flow.emit.folding.summary
import sys
import ast
import json
import argparse
from typing import List, Tuple, Optional, Any
from pathlib import Path
from watcher.plane.emitter import get_emitter
from phase.bind.resolver import find_current_self
from arch.contract.registry.unified import contract, manifold_node
from phase.runtime.cli.executor import dispatch_cli, CliTaskAdapter, parse_local
from arch.proto.phase.projector import PhaseProjector
from arch.proto.phase.ator import PhaseAtor
from arch.proto.phase.flow import PhaseFlow, FlowState
from arch.contract.protocol import Proto, proto

log = get_emitter("folding.summary")
T_Rep = Tuple[Path, Optional[str]]
T_Surface = dict

class RepoFolder(PhaseProjector[Path, Path, T_Rep, T_Surface]):
    """
    @desc: Theoria - Projector (Folding)
    @role: 파일 시스템 위상(Φ)을 스캔하여 계층형 JSON 표면(Φs)으로 투영
    """
    IGNORE_DIRS = {
        '__pycache__', 'venv', '.venv', 'env', 
        'node_modules', 'dist', 'build', '.git', '.idea'
    }

    def __init__(self, target_dir: Path):
        super().__init__()
        self.target_dir = target_dir

    def scan(self) -> List[Path]:
        if not self.target_dir.exists() or not self.target_dir.is_dir():
            log.error(f"[Emit Error] Directory not found: {self.target_dir}")
            return []
        return list(self.target_dir.rglob('*'))

    def select(self, topology: List[Path], context: Path) -> List[Path]:
        valid_nodes = []
        for filepath in topology:
            if any(part in self.IGNORE_DIRS for part in filepath.parts):
                continue
            if not filepath.is_file() or filepath.suffix not in ['.py', '.md']:
                continue
            valid_nodes.append(filepath)
        return valid_nodes

    def project(self, subgraph: List[Path], context: Path) -> List[T_Rep]:
        representations = []
        for filepath in subgraph:
            meta_text = None
            if filepath.suffix == '.md':
                meta_text = self._extract_md(filepath)
            elif filepath.suffix == '.py':
                meta_text = self._extract_py(filepath)
            representations.append((filepath, meta_text))
        return representations

    def assemble(self, representations: List[T_Rep], context: Path) -> T_Surface:
        arch_blueprint = {}
        topology_tree = {}

        self._build_dynamic_arch(context, arch_blueprint)
        for filepath, meta_text in representations:
            rel_path = filepath.relative_to(context)
            parts = rel_path.parts
            current_node = topology_tree

            for part in parts[:-1]:
                if part not in current_node:
                    current_node[part] = {}
                current_node = current_node[part]

            filename = parts[-1]
            if meta_text:
                current_node[filename] = meta_text
            else:
                if "files" not in current_node:
                    current_node["files"] = []
                current_node["files"].append(filename)

        return {"arch": arch_blueprint, "topology": topology_tree}

    def emit(self, surface: T_Surface, context: Path) -> None:
        emitted_json = json.dumps(surface, indent=2, ensure_ascii=False)
        log.info(emitted_json)

    def _extract_md(self, filepath: Path) -> Optional[str]:
        extracted = []
        in_title_section = False
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('# '): in_title_section = True; continue
                    if in_title_section:
                        if line.startswith('@'): extracted.append(line)
                        elif line.startswith('#') or (line == "" and len(extracted) > 0): break
        except Exception: return None
        return " ".join(extracted).replace('\n', ' ') if extracted else None

    def _extract_py(self, filepath: Path) -> Optional[str]:
        extracted = []
        try:
            with open(filepath, 'r', encoding='utf-8') as f: content = f.read()
            tree = ast.parse(content)
            docstring = ast.get_docstring(tree)
            if docstring: extracted.append(docstring.replace('\n', ' ').strip())
        except Exception: pass
        
        in_title_section = False
        for line in content.split('\n'):
            line = line.strip()
            if line.startswith('#') and not line.startswith('##') and 'title' in line.lower():
                in_title_section = True; continue
            if in_title_section:
                if line.startswith('##'): extracted.append(line.lstrip('#').strip())
                elif line and not line.startswith('#') and not line.startswith('"""') and not line.startswith("'''"): break
        return " | ".join(extracted) if extracted else None

    def _build_dynamic_arch(self, context: Path, target_dict: dict) -> None:
        def is_valid(d: Path): return d.is_dir() and not d.name.startswith('.') and d.name not in self.IGNORE_DIRS
        root_subs = [d.name for d in context.iterdir() if is_valid(d)]
        if root_subs: target_dict[f"{context.name}.desc"] = " ".join(root_subs)
        for domain_dir in context.iterdir():
            if is_valid(domain_dir):
                domain_subs = [d.name for d in domain_dir.iterdir() if is_valid(d)]
                if domain_subs: target_dict[f"{domain_dir.name}.desc"] = " ".join(domain_subs)


class FoldingOperator:
    pass

@manifold_node(name="emit.folding", requires=[], emits=["folding"])
@proto(Proto((PhaseFlow, FoldingOperator, "dict"), kind="folding"))
class FoldingAtor(PhaseAtor):
    def __init__(self, spec):
        self.next = spec["next"]
        self.target_repo = spec.get("target_repo", "surgent")

    async def run(self, flow: PhaseFlow, operator: Any, ctx: FlowState) -> List[Tuple[str, FlowState]]:
        log.info(f"    [FoldingAtor] Initiating topology projection for ψ:{flow.id}")
        
        repo_name = flow.payload.get("target_repo", self.target_repo)
        target_dir = find_current_self() / repo_name
        
        projector = RepoFolder(target_dir=target_dir)
        surface = projector.compile(context=target_dir)
        
        flow.payload["topology_surface"] = surface
        ctx.state["last_folded_repo"] = repo_name
        
        return [(self.next, ctx)]


def entry_task(args):
    parser = argparse.ArgumentParser(description="Standalone CLI execution for FoldingProjector")
    parser.add_argument('--repo', type=str, required=True, help="Target folder name to scan")
    parsed_args = parser.parse_args(args)
    
    target_dir = find_current_self() / parsed_args.repo
    projector = RepoFolder(target_dir=target_dir)
    return CliTaskAdapter(lambda: projector.compile(context=target_dir))

@contract.cli(name="folding.summary", recept=[])
def main():
    bound_args, remain = parse_local(sys.argv[1:])
    if bound_args.local:
        entry_task(remain).run()
    else:
        dispatch_cli("folding.summary", entry_task, __file__)

if __name__ == "__main__":
    main()