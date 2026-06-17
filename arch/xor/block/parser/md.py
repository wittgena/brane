# arch.xor.block.parser.md
## @lineage: hub.xor.block.parser.md
## @lineage: arch.code.block.parser.md
## @lineage: arch.model.code.block.parser.md
## @lineage: arch.project.block.parser.md
## @lineage: xphi.code.block.parser.md
## @lineage: topos.arch.block.parser.md
## @lineage: arch.model.block.parser.md
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Union, Dict
from arch.xor.block.schema import MdDocument, Heading, MdSection, MdNode, CodeBlock, Paragraph

## Markdown → AST
class MdAstParser:
    def __init__(self, source: str, is_file: bool = True):
        """
        :param source: 파일 경로(str) 또는 마크다운 텍스트 원문(str)
        :param is_file: True면 source를 파일 경로로 인식, False면 메모리 상의 텍스트로 인식
        """
        self.is_file = is_file
        if self.is_file:
            self.path = Path(source)
            self.raw_text = None
        else:
            self.path = Path("<memory_topology>")  # MdDocument 호환성을 위한 가상 Path
            self.raw_text = source

    def parse(self) -> MdDocument:
        # 파일/메모리 분기 처리
        if self.is_file:
            if not self.path.exists():
                raise FileNotFoundError(f"File not found: {self.path}")
            text = self.path.read_text(encoding="utf-8")
        else:
            text = self.raw_text

        lines = text.splitlines()

        root_sections: List[MdSection] = []
        section_stack: List[MdSection] = []
        current_section: Optional[MdSection] = None

        inside_code = False
        code_lang = ""
        code_buffer: List[str] = []
        paragraph_buffer: List[str] = []

        def flush_paragraph():
            nonlocal paragraph_buffer
            if paragraph_buffer and current_section:
                content = "\n".join(paragraph_buffer).strip()
                if content and content != "---":
                    current_section.children.append(Paragraph(content))
            paragraph_buffer = []

        for line in lines:
            ## Heading
            heading_match = re.match(r"(#{1,6})\s+(.*)", line)
            if heading_match and not inside_code:
                flush_paragraph()

                level = len(heading_match.group(1))
                title = heading_match.group(2).strip()
                meta_tag = title.startswith("@")
                new_section = MdSection(level, title, meta_tag)
                new_section.children.append(Heading(level=level, content=title))

                while section_stack and section_stack[-1].level >= level:
                    section_stack.pop()

                if section_stack:
                    section_stack[-1].subsections.append(new_section)
                else:
                    root_sections.append(new_section)

                section_stack.append(new_section)
                current_section = new_section
                continue

            ## Code block start / end
            code_match = re.match(r"```([\w\.\-]+)?", line.strip())
            if code_match:
                if not inside_code:
                    flush_paragraph()
                    inside_code = True
                    code_lang = code_match.group(1) or "plain"
                    code_buffer = []
                else:
                    inside_code = False
                    if current_section:
                        current_section.children.append(
                            CodeBlock(code_lang, "\n".join(code_buffer).strip())
                        )
                    code_buffer = []
                continue

            if inside_code:
                code_buffer.append(line)
                continue

            ## Paragraph
            if current_section:
                if line.strip() == "":
                    flush_paragraph()
                else:
                    paragraph_buffer.append(line)

        flush_paragraph()
        return MdDocument(self.path, root_sections)

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