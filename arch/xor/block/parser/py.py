# arch.xor.block.parser.py
## @lineage: hub.xor.block.parser.py
## @lineage: arch.code.block.parser.py
## @lineage: arch.model.code.block.parser.py
## @lineage: arch.project.block.parser.py
## @lineage: xphi.code.block.parser.py
## @lineage: topos.arch.block.parser.py
## @lineage: arch.model.block.parser.py
import re
import ast
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Union, Dict
from arch.xor.block.schema import MdDocument, MdSection, MdNode, CodeBlock, Paragraph

## Python → AST (using Python builtin ast module)
class PyAstParser:
    def __init__(self, path: Union[str, Path]):
        self.path = Path(path)

    def parse(self) -> MdDocument:
        if not self.path.exists():
            raise FileNotFoundError(f"File not found: {self.path}")

        source_code = self.path.read_text(encoding="utf-8")
        lines = source_code.splitlines(keepends=True)
        
        # 파일 전체를 감싸는 Root Section
        root_section = MdSection(level=1, title=self.path.name, meta_tag=False)
        
        # 1. 메타데이터 추출 (기존 로직 유지 - main 함수의 docstring)
        docstring = self._extract_main_docstring(lines)
        if docstring:
            metadata = self._parse_docstring(docstring)
            for key, value in metadata.items():
                meta_section = MdSection(level=2, title=f"@{key}", meta_tag=True)
                content = value.strip()
                if content:
                    meta_section.children.append(Paragraph(text=content))
                root_section.subsections.append(meta_section)

        # 2. Python AST 파싱을 통한 자동 청킹 (Chunking)
        try:
            tree = ast.parse(source_code)
            self._split_into_blocks(tree, source_code, root_section)
        except SyntaxError as e:
            # 문법 오류가 있는 파일은 Fallback으로 전체를 하나의 블록으로 처리
            err_section = MdSection(level=2, title="py.script (syntax_error)", meta_tag=False)
            err_section.children.append(CodeBlock(lang="python", content=source_code.strip()))
            root_section.subsections.append(err_section)

        return MdDocument(self.path, [root_section])

    def _split_into_blocks(self, tree: ast.Module, source_code: str, root_section: MdSection):
        """AST 노드를 순회하며 클래스, 함수, 전역 코드를 별도의 Section으로 분리합니다."""
        global_lines = []

        for node in tree.body:
            # Python 3.8+ 이상에서 지원하는 get_source_segment 활용
            node_code = ast.get_source_segment(source_code, node)
            if not node_code:
                continue

            if isinstance(node, ast.ClassDef):
                # 클래스 블록
                sec = MdSection(level=2, title=f"class:{node.name}", meta_tag=False)
                sec.children.append(CodeBlock(lang="python", content=node_code))
                root_section.subsections.append(sec)

            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # 함수 블록 (main 함수도 여기 포함됨)
                sec = MdSection(level=2, title=f"func:{node.name}", meta_tag=False)
                sec.children.append(CodeBlock(lang="python", content=node_code))
                root_section.subsections.append(sec)

            else:
                # Import, 전역 변수 등 모듈 레벨 코드 수집
                global_lines.append(node_code)

        # 수집된 모듈 레벨 코드가 있다면 하나의 Section으로 병합
        if global_lines:
            sec = MdSection(level=2, title="module_globals", meta_tag=False)
            sec.children.append(CodeBlock(lang="python", content="\n".join(global_lines)))
            # 전역 코드는 가독성을 위해 맨 앞으로(메타데이터 바로 뒤) 삽입하는 것도 좋은 방법입니다.
            root_section.subsections.insert(len(root_section.subsections), sec)


    def _extract_main_docstring(self, lines: List[str]) -> str:
        # 기존 로직과 동일
        doc_lines = []
        in_doc = False
        for i, line in enumerate(lines):
            if line.strip().startswith("def main("):
                for j in range(i + 1, len(lines)):
                    l = lines[j].strip()
                    if l.startswith('"""') or l.startswith("'''"):
                        if not in_doc:
                            in_doc = True
                            doc_lines.append(l.lstrip("\"'"))
                            if (l.endswith('"""') and len(l) > 3) or (l.endswith("'''") and len(l) > 3):
                                doc_lines[-1] = doc_lines[-1].rstrip("\"'")
                                break
                        else:
                            doc_lines.append(l.rstrip("\"'"))
                            break
                    elif in_doc:
                        doc_lines.append(l)
                break
        return "\n".join(doc_lines)

    def _parse_docstring(self, doc: str) -> Dict[str, str]:
        # 기존 로직과 동일
        sections = {}
        current = None
        for line in doc.splitlines():
            line = line.strip()
            if line.startswith("@"):
                tag, _, value = line.partition(":")
                current = tag.strip("@")
                sections[current] = value.strip()
            elif current and line:
                sections[current] += "\n" + line
        return sections

class PyDotMdParser:
    """
    @py.start ~ @py.end 마커 기반의 정적 스크립트 추출 및 
    main() 함수의 docstring 메타데이터를 파싱하여 MdDocument 모델로 변환하는 클래스
    """
    def __init__(self, path: Union[str, Path]):
        self.path = Path(path)

    def parse(self) -> MdDocument:
        if not self.path.exists():
            raise FileNotFoundError(f"File not found: {self.path}")

        lines = self.path.read_text(encoding="utf-8").splitlines(keepends=True)
        
        # 1. @py.start ~ @py.end 블록 추출
        code_lines = self._extract_py_block(lines)
        code_content = "".join(code_lines).strip()
        
        # 2. main 함수 docstring 기반 메타데이터 추출
        docstring = self._extract_main_docstring(lines)
        metadata = self._parse_docstring(docstring)
        
        # 3. MdDocument 객체 모델 구축
        root_section = MdSection(level=1, title=self.path.name, meta_tag=False)
        
        # 지정된 순서대로 메타데이터 Section 추가 (desc, input, output, example 등)
        target_keys = ["desc", "input", "output", "example"]
        for key in target_keys:
            if key in metadata:
                meta_section = MdSection(level=2, title=f"@{key}", meta_tag=True)
                meta_section.children.append(Paragraph(text=metadata[key].strip()))
                root_section.subsections.append(meta_section)
                
        # 기본 키 외에 추가로 파싱된 메타데이터가 있다면 덧붙임
        for key, value in metadata.items():
            if key not in target_keys:
                meta_section = MdSection(level=2, title=f"@{key}", meta_tag=True)
                meta_section.children.append(Paragraph(text=value.strip()))
                root_section.subsections.append(meta_section)

        # 4. py.script Section에 추출된 코드 블록 추가
        script_section = MdSection(level=2, title="py.script", meta_tag=False)
        if code_content:
            script_section.children.append(CodeBlock(lang="python", content=code_content))
        root_section.subsections.append(script_section)

        return MdDocument(self.path, [root_section])

    def _extract_py_block(self, lines: List[str]) -> List[str]:
        in_block = False
        collected = []

        for line in lines:
            if "# @py.start" in line:
                in_block = True

            if in_block:
                collected.append(line)

            if in_block and "# @py.end" in line:
                break

        return collected

    def _extract_main_docstring(self, lines: List[str]) -> str:
        doc_lines = []
        in_doc = False
        for i, line in enumerate(lines):
            if line.strip().startswith("def main("):
                for j in range(i + 1, len(lines)):
                    l = lines[j].strip()
                    if l.startswith('"""') or l.startswith("'''"):
                        if not in_doc:
                            in_doc = True
                            doc_lines.append(l.lstrip("\"'"))
                            # 한 줄짜리 docstring 처리
                            if (l.endswith('"""') and len(l) > 3) or (l.endswith("'''") and len(l) > 3):
                                doc_lines[-1] = doc_lines[-1].rstrip("\"'")
                                break
                        else:
                            doc_lines.append(l.rstrip("\"'"))
                            break
                    elif in_doc:
                        doc_lines.append(l)
                break
        return "\n".join(doc_lines)

    def _parse_docstring(self, doc: str) -> Dict[str, str]:
        sections = {}
        current = None
        for line in doc.splitlines():
            line = line.strip()
            if line.startswith("@"):
                tag, _, value = line.partition(":")
                current = tag.strip("@")
                sections[current] = value.strip()
            elif current and line:
                sections[current] += "\n" + line
        return sections