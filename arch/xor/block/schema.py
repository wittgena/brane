# arch.xor.block.schema
## @lineage: hub.xor.block.schema
## @lineage: arch.code.block.schema
## @lineage: arch.model.code.block.schema
## @lineage: arch.project.block.schema
## @lineage: xphi.code.block.schema
## @lineage: topos.arch.block.schema
## @lineage: arch.model.block.schema
from dataclasses import dataclass, field
from typing import List, Optional, Union, Dict
from pathlib import Path

@dataclass
class Contract:
    kind: Optional[str] = None
    name: Optional[str] = None
    features: List[str] = field(default_factory=list)
    refs: List[str] = field(default_factory=list)
    location: Optional[str] = None
    source: Optional[str] = None

## AST Node Definitions
class MdNode:
    pass

@dataclass
class Heading(MdNode):
    level: int
    content: str
    type: str = "heading"  # SpecTranscript가 필터링하는 타입명

@dataclass
class Paragraph(MdNode):
    text: str

@dataclass
class CodeBlock(MdNode):
    lang: str
    content: str

@dataclass
class MdSection:
    level: int
    title: str
    meta_tag: bool
    children: List[MdNode] = field(default_factory=list)
    subsections: List["MdSection"] = field(default_factory=list)

@dataclass
class MdDocument:
    path: Path
    sections: List[MdSection]