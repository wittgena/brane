# arch.xor.block.parser.topos
## @lineage: hub.xor.block.parser.topos
## @lineage: arch.code.block.parser.topos
## @lineage: arch.model.code.block.parser.topos
## @lineage: arch.project.block.parser.topos
## @lineage: xphi.code.block.parser.topos
## @lineage: topos.arch.block.parser.topos
## @lineage: arch.model.block.parser.topos
import re
import ast
import tokenize
import io
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Union, Dict
from arch.xor.block.schema import MdDocument, MdSection, MdNode, CodeBlock, Paragraph

class ToposAstParser:
    """
    위상 기호(Φ, ∂, Δ 등)를 보존하고 Python AST를 활용하여 
    코드의 구조와 위상 흐름을 추출하는 개선된 파서.
    """
    
    def __init__(self, path: Union[str, Path]):
        self.path = Path(path)
        self.source_code = self.path.read_text(encoding="utf-8")
        # 위상 기호 패턴 (Φ: 상태, ∂: 경계, Δ: 변이, =>: 흐름)
        self.topos_pattern = r'[Φ∂ΔΣ|⇒→=>\-+]+'

    def parse(self) -> MdDocument:
        if not self.path.exists():
            raise FileNotFoundError(f"파일을 찾을 수 없습니다: {self.path}")

        tree = ast.parse(self.source_code)
        root_section = MdSection(level=1, title=self.path.name, meta_tag=False)

        # 1. 모듈 레벨 위상 메타데이터 (Module Docstring)
        module_doc = ast.get_docstring(tree)
        if module_doc:
            self._process_topos_docstring(module_doc, root_section)

        # 2. 코드 내 특수 주석 위상 추출 (tokenize 활용)
        self._extract_comment_topology(root_section)

        # 3. AST 기반 구조 분해
        self._split_into_topos_blocks(tree, root_section)

        return MdDocument(self.path, [root_section])

    def _process_topos_docstring(self, docstring: str, parent_section: MdSection):
        """Docstring 내의 @tag 및 위상 기호를 해석하여 섹션화합니다."""
        current_tag = None
        tag_content = []

        for line in docstring.splitlines():
            line = line.strip()
            if line.startswith("@"):
                if current_tag:
                    self._add_meta_section(current_tag, "\n".join(tag_content), parent_section)
                
                tag_part, _, desc = line.partition(":")
                current_tag = tag_part.strip("@")
                tag_content = [desc.strip()]
            elif current_tag:
                tag_content.append(line)
        
        if current_tag:
            self._add_meta_section(current_tag, "\n".join(tag_content), parent_section)

    def _add_meta_section(self, title: str, content: str, parent: MdSection):
        sec = MdSection(level=2, title=f"@{title}", meta_tag=True)
        if content.strip():
            sec.children.append(Paragraph(text=content.strip()))
        parent.subsections.append(sec)

    def _extract_comment_topology(self, root_section: MdSection):
        """# Φ -> ∂ 같은 특수 주석을 추출하여 위상 섹션으로 추가합니다."""
        tokens = tokenize.generate_tokens(io.StringIO(self.source_code).readline)
        topos_comments = []
        
        for toktype, tokval, _, _, _ in tokens:
            if toktype == tokenize.COMMENT:
                # 위상 기호가 포함된 주석 필터링
                if any(sym in tokval for sym in "Φ∂ΔΣ⇒→"):
                    topos_comments.append(tokval.strip("# ").strip())
        
        if topos_comments:
            comment_sec = MdSection(level=2, title="Φ.topos.flow", meta_tag=True)
            comment_sec.children.append(Paragraph(text="\n".join(topos_comments)))
            root_section.subsections.append(comment_sec)

    def _split_into_topos_blocks(self, tree: ast.Module, root_section: MdSection):
        """AST 노드를 순회하며 위상적 단위(Class/Func)로 분리합니다."""
        for node in tree.body:
            node_code = ast.get_source_segment(self.source_code, node)
            if not node_code: continue

            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                prefix = "class" if isinstance(node, ast.ClassDef) else "func"
                sec = MdSection(level=2, title=f"{prefix}:{node.name}", meta_tag=False)
                
                # 내부 Docstring 추출 (있는 경우)
                inner_doc = ast.get_docstring(node)
                if inner_doc:
                    sec.children.append(Paragraph(text=f"Role: {inner_doc.splitlines()[0]}"))
                
                sec.children.append(CodeBlock(lang="python", content=node_code))
                root_section.subsections.append(sec)
            
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                # 임포트 섹션 별도 관리 (의존성 위상)
                dep_sec = next((s for s in root_section.subsections if s.title == "dependencies"), None)
                if not dep_sec:
                    dep_sec = MdSection(level=2, title="dependencies", meta_tag=True)
                    root_section.subsections.insert(0, dep_sec)
                dep_sec.children.append(CodeBlock(lang="python", content=node_code))
