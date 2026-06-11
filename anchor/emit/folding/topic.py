# anchor.emit.folding.topic
## @lineage: meta.flow.emit.folding.topic
## @lineage: meta.flow.folding.topic
import os
import sys
import re
import asyncio
import argparse
import fnmatch
from abc import ABC, abstractmethod
from typing import Generic, TypeVar, List, Tuple, Dict, Any, Optional
from pathlib import Path
from collections import defaultdict
from phase.bind.resolver import find_current_self, resolve_path, get_invoker
from arch.contract.registry.unified import contract
from watcher.plane.emitter import get_emitter
from arch.proto.phase.projector import PhaseProjector
from phase.runtime.cli.executor import execute_cli_task, CliTaskAdapter, dispatch_cli, parse_local
from arch.xor.block.parser.py import PyDotMdParser 

log = get_emitter("folding.topic")

DELIMITER = "#####"

class TopicFolder(PhaseProjector[Path, Optional[Dict[str, Any]], Tuple[str, str], Dict[str, str]]):
    def __init__(self, target_repo: str):
        try:
            self.self_root = find_current_self()
            self.io_root = resolve_path('io')
        except Exception as e:
            log.error(f"[error] 기준면(.self)을 찾을 수 없음: {e}")
            sys.exit(1)

        self.merge_root = self.self_root / target_repo
        self.emit_root = self.io_root / "topic" / f"{target_repo}"

        if not self.merge_root.exists():
            log.info(f"[error] 입력 경로 없음: {self.merge_root}")
            sys.exit(1)

        self.ignore_patterns = self._load_gitignore_patterns()
        log.info(f"[merge.from] {self.merge_root}")
        log.info(f"[emit.to] {self.emit_root}")

    def _load_gitignore_patterns(self) -> List[str]:
        patterns = [
            "*.jar", "*.class", "*.log", "*.pyc", "*.exe", "build/**", "gradle/**", "gradlew", "gradlew.bat",
            "__pycache__/**", ".venv/**", ".idea/**", ".git/**", ".DS_Store", "node_modules/**", ".tab"
        ]
        for gitignore_path in [self.merge_root / ".gitignore", Path.home() / ".gitignore"]:
            if gitignore_path.exists():
                with open(gitignore_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            patterns.append(line)
                break
        log.info(f"[IGNORE] 적용된 패턴 수: {len(patterns)}")
        return patterns

    def _is_binary_file(self, path: Path, sample_size: int = 1024) -> bool:
        if path.suffix == '.md': return False
        try:
            with path.open("rb") as f:
                chunk = f.read(sample_size)
                if b'\0' in chunk: return True
                text_ratio = sum(32 <= b <= 126 or b in (9, 10, 13) for b in chunk) / max(len(chunk), 1)
                return text_ratio < 0.8
        except Exception as e:
            log.error(f"[BINARY CHECK ERROR] {path}: {e}")
            return True # 오류 시 보수적으로 제외

    def _should_exclude(self, path: Path) -> bool:
        rel_path = str(path.relative_to(self.merge_root))
        rel_path_obj = path.relative_to(self.merge_root)

        for pattern in self.ignore_patterns:
            if pattern.endswith("/**") and rel_path_obj.match(pattern): return True
            elif pattern.endswith("/") and rel_path.startswith(pattern): return True
            elif fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(path.name, pattern): return True

        if any(p.startswith(".") for p in rel_path_obj.parts): return True
        if self._is_binary_file(path): return True
        return False

    def _extract_title(self, content: str, fallback: str, prefix="@phase") -> str:
        lines = content.splitlines()
        for line in lines:
            if re.match(r"^#\s+\S", line): return f"## {prefix}: {line.lstrip('#').strip()}"
        for line in lines:
            if re.match(r"^##\s+\S", line): return f"## {prefix}: {line.lstrip('#').strip()}"
        return f"## @file: {Path(fallback).stem.replace('_', ' ')}"

    def _get_group_key(self, md_path: Path, level: int = 1) -> str:
        rel = md_path.relative_to(self.merge_root)
        parts = rel.parts[:-1]
        return "root" if not parts else ".".join(parts[:level])

    def _render_md_node(self, node: Any) -> str:
        node_type = type(node).__name__
        if node_type == "MdDocument":
            return "".join(self._render_md_node(sec) for sec in getattr(node, 'sections', []))
        elif node_type == "MdSection":
            res = [f"{'#' * node.level} {node.title}\n\n"]
            for child in getattr(node, 'children', []):
                res.append(self._render_md_node(child))
            for sub in getattr(node, 'subsections', []):
                res.append(self._render_md_node(sub))
            return "".join(res)
        elif node_type == "Paragraph":
            return f"{node.text}\n\n"
        elif node_type == "CodeBlock":
            content = node.content if node.content.endswith('\n') else node.content + '\n'
            return f"```{node.lang}\n{content}```\n\n"
        return ""

    def select(self, topos: List[Path], context: Optional[Dict[str, Any]] = None) -> List[Path]:
        return [p for p in topos if p.is_file() and not self._should_exclude(p)]

    def scan(self) -> List[Path]:
        return list(self.merge_root.rglob("*"))

    def filter(self, topos: List[Path]) -> List[Path]:
        return [p for p in topos if p.is_file() and not self._should_exclude(p)]

    def topic(self, subgraph: List[Path], context: Optional[Dict[str, Any]] = None) -> List[Tuple[str, str]]:
        representations = []
        for path in subgraph:
            try:
                key = self._get_group_key(path)
                
                if path.suffix == ".py":
                    try:
                        # [수정됨] 객체 지향 Parser 활용
                        parser = PyDotMdParser(path)
                        doc = parser.parse()
                        
                        root = getattr(doc, 'sections', [])[0]
                        
                        # Fallback 트리거를 위한 필수 요소 검증 (desc와 코드 블록 유무)
                        has_desc = any(sub.title == "@desc" for sub in getattr(root, 'subsections', []))
                        has_script = any(
                            sub.title == "py.script" and any(type(c).__name__ == "CodeBlock" and c.content.strip() for c in getattr(sub, 'children', []))
                            for sub in getattr(root, 'subsections', [])
                        )

                        if not has_desc or not has_script:
                            raise ValueError("dotmd 요소 부족 (fallback 발생)")

                        # AST를 마크다운 문자열로 렌더링
                        content = self._render_md_node(doc).strip()
                        
                    except Exception as e:
                        ## Fallback: Plain python code
                        log.debug(f"[FALLBACK] {path.name}: {e}")
                        content = f"```python\n{path.read_text(encoding='utf-8', errors='replace')}\n```"
                else:
                    ## 일반 텍스트
                    content = path.read_text(encoding="utf-8", errors="replace").strip()

                title_line = self._extract_title(content, path.name)
                final_block = f"{DELIMITER} {title_line}\n\n{content}\n"
                representations.append((key, final_block))
                
            except Exception as e:
                log.error(f"[topic ERROR] {path}: {e}")
                
        return representations

    def assemble(self, representations: List[Tuple[str, str]], context: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
        groups = defaultdict(list)
        for key, text in representations:
            groups[key].append(text)
        return {key: "\n".join(texts) for key, texts in groups.items()}

    def emit(self, surface: Dict[str, str], context: Optional[Dict[str, Any]] = None) -> None:
        self.emit_root.mkdir(parents=True, exist_ok=True)
        for key, content in surface.items():
            out_path = self.emit_root / f"{key}.md"
            try:
                out_path.write_text(content, encoding="utf-8")
                log.info(f"[WRITE] → {out_path}")
            except Exception as e:
                log.error(f"[WRITE ERROR] {out_path}: {e}")

def entry_task(args):
    parser = argparse.ArgumentParser(description="Compile topic bundle into a grouped markdown.")
    parser.add_argument("--repo", type=str, required=True, help="Target input path. E.g., flow/dev")
    args = parser.parse_args(args)
    compiler = TopicFolder(target_repo=args.repo)
    return CliTaskAdapter(compiler.compile)

@contract.cli(name="topic.bundle", recept=[])
def main():
    bound_args, remain = parse_local(sys.argv[1:])
    if bound_args.local:
        entry_task(remain).run()
    else:
        dispatch_cli("topic.bundle", entry_task, __file__)

if __name__ == "__main__":
    main()