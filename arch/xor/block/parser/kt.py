# arch.xor.block.parser.kt
## @lineage: hub.xor.block.parser.kt
## @lineage: arch.code.block.parser.kt
## @lineage: arch.model.code.block.parser.kt
## @lineage: arch.project.block.parser.kt
## @lineage: xphi.code.block.parser.kt
## @lineage: topos.arch.block.parser.kt
## @lineage: arch.model.block.parser.kt
import re
from pathlib import Path
from typing import List, Tuple
from arch.xor.block.schema import MdDocument, MdSection, CodeBlock, Paragraph, Contract

class KtAstParser:
    def __init__(self, path: Path, contracts: List[Contract] = None):
        self.path = path
        self.contracts = contracts or []

    def parse(self) -> MdDocument:
        doc = MdDocument(path=self.path, sections=[])

        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except Exception as e:
            section = MdSection(title="error", level=1, meta_tag="")
            section.children.append(Paragraph(text=f"Failed to read file: {e}"))
            doc.sections.append(section)
            return doc

        if not self.contracts:
            section = MdSection(title="file_root", level=1, meta_tag="")
            section.children.append(CodeBlock(lang="kotlin", content="\n".join(lines)))
            doc.sections.append(section)
            return doc

        # 1. location에서 (시작줄, 끝줄) 파싱
        parsed_contracts: List[Tuple[int, int, Contract]] = []
        for f in self.contracts:
            start_line, end_line = self._parse_location(f.location, len(lines))
            parsed_contracts.append((start_line, end_line, f))

        # 2. 정렬: 시작줄은 오름차순, 끝줄은 내림차순 
        # (이렇게 해야 큰 범위인 Class가 먼저 오고, 내부의 Function이 뒤에 옴)
        parsed_contracts.sort(key=lambda x: (x[0], -x[1]))

        root_sections = []
        stack = []  # 계층 구조(Nesting) 추적을 위한 스택

        for start_line, end_line, fact in parsed_contracts:
            kind = fact.kind or "block"
            name = fact.name or "unnamed"
            title = f"{kind}::{name}"
            meta_tag = self._build_meta_tag(fact)

            start_idx = max(0, start_line - 1)
            end_idx = min(len(lines), end_line)
            block_content = "\n".join(lines[start_idx:end_idx]).strip()

            if not block_content:
                continue

            # 현재 블록의 시작줄이 스택 최상단 블록의 끝줄을 벗어났다면 (형제 노드 혹은 상위 노드로 이동)
            while stack and stack[-1][0] < start_line:
                stack.pop()

            level = len(stack) + 1
            section = MdSection(title=title, level=level, meta_tag=meta_tag)
            section.children.append(CodeBlock(lang="kotlin", content=block_content))

            if stack:
                # 스택에 부모가 있다면 부모의 subsection으로 편입 (예: 클래스 하위의 함수)
                stack[-1][1].subsections.append(section)
            else:
                # 부모가 없다면 최상위 노드
                root_sections.append(section)

            # 현재 섹션을 스택에 푸시 (종료줄, 섹션 객체)
            stack.append((end_line, section))

        doc.sections.extend(root_sections)
        return doc

    def _parse_location(self, location: str, max_lines: int) -> Tuple[int, int]:
        """
        포맷 "start:end" 를 파싱. 매칭 실패시 기본값 반환.
        """
        if not location:
            return 1, max_lines
        
        m = re.match(r'^(\d+):(\d+)$', location)
        if m:
            return int(m.group(1)), int(m.group(2))
            
        m_single = re.match(r'^(\d+)$', location)
        if m_single:
            return int(m_single.group(1)), int(m_single.group(1))
            
        return 1, max_lines

    def _build_meta_tag(self, fact: Contract) -> str:
        meta = []
        if fact.features:
            meta.append(f"features=[{','.join(fact.features)}]")
        if fact.refs:
            meta.append(f"refs=[{','.join(fact.refs)}]")
            
        return " | ".join(meta) if meta else ""