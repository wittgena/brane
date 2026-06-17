# arch.xor.block.extractor
import re
import sys
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Union, Dict
from watcher.plane.emitter import get_logger
from phase.bind.resolver import find_current_self, resolve_path
from arch.xor.block.schema import MdDocument, Heading, MdSection, MdNode, CodeBlock, Paragraph
from arch.xor.block.parser.md import MdAstParser
from arch.xor.block.parser.py import PyAstParser
from arch.xor.block.parser.kt import KtAstParser 

log = get_logger("block.extractor")

@dataclass
class Block:
    """Kotlin의 subst.xor.Block 과 1:1로 매칭되는 순수 파이썬 도메인 객체"""
    block_id: str
    file_path: str
    source_type: str
    section: str
    section_path: str
    section_depth: int
    block_type: str
    order_index: int
    symbols: List[str]
    content: Optional[str] = None
    meta: Optional[str] = None
    dsl_name: Optional[str] = None

    def to_dict(self) -> dict:
        """JSON 직렬화 및 추후 LlamaIndex Node 메타데이터 변환을 위한 헬퍼 메서드"""
        return asdict(self)

class BlockExtractor:
    def __init__(self):
        self.counter = 0

    # 반환 타입을 List[dict] -> List[Block]으로 변경
    def extract(self, doc: MdDocument) -> List[Block]:
        blocks: List[Block] = []
        source_type = doc.path.suffix.lstrip(".") or "txt"

        def walk(section: MdSection, parent_path="", depth=0):
            section_path = (
                f"{parent_path}/{section.title}"
                if parent_path else section.title
            )

            for node in section.children:
                block_type = None
                content = None
                dsl_name = None

                if isinstance(node, Paragraph):
                    block_type = "paragraph"
                    content = node.text.strip()
                elif isinstance(node, CodeBlock):
                    block_type = node.lang
                    content = node.content.strip()
                    # DSL name extraction
                    if content.startswith("@"):
                        first_line = content.splitlines()[0]
                        dsl_name = first_line.split()[0].strip("@")
                elif isinstance(node, Heading):
                    block_type = "heading"
                    content = node.content.strip()

                if content: 
                    # 딕셔너리 대신 Block 데이터 클래스 인스턴스 생성
                    block = Block(
                        block_id=f"{doc.path}::{self.counter}",
                        file_path=str(doc.path),
                        source_type=source_type,
                        section=section.title,
                        section_path=section_path,
                        section_depth=depth,
                        block_type=block_type,
                        meta=section.meta_tag,
                        order_index=self.counter,
                        symbols=self._extract_symbols(section, block_type),
                        content=content,
                        dsl_name=dsl_name
                    )

                    blocks.append(block)
                    self.counter += 1

            for sub in section.subsections:
                walk(sub, section_path, depth + 1)

        for root in doc.sections:
            walk(root, depth=0)

        return blocks

    def _extract_symbols(self, section: MdSection, block_type: str) -> List[str]:
        symbols = []
        if block_type:
            symbols.append(block_type)

        tokens = re.split(r"[^\w\.]+", section.title)
        symbols.extend([t for t in tokens if t])

        if section.meta_tag:
            meta_tokens = re.split(r"[^\w\.]+", str(section.meta_tag))
            symbols.extend([t for t in meta_tokens if t and t not in ("features", "refs")])

        return list(set(symbols))

def extract_block_from_file(path: Path, kt_contracts: dict = None) -> List[Block]:
    """파일의 AST를 파싱하고 Extractor를 통해 Block 객체 리스트를 반환"""
    if path.suffix == ".md":
        parser = MdAstParser(path)
    elif path.suffix == ".py":
        parser = PyAstParser(path)
    elif path.suffix == ".kt":
        file_contracts = kt_contracts.get(str(path.absolute()), []) if kt_contracts else []
        parser = KtAstParser(path, file_contracts)
    else:
        log.warning(f"[skip] 지원하지 않는 확장자: {path}")
        return []

    doc = parser.parse()
    extractor = BlockExtractor()
    return extractor.extract(doc)