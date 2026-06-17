# arch.xor.manifold.sign.contract
## @lineage: xor.adapter.manifold.sign.contract
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class ContractSpec(BaseModel):
    """코드 내에 바인딩된 입출력 계약 명세"""
    requires: List[str] = Field(default_factory=list)
    emits: List[str] = Field(default_factory=list)
    evidence: str = ""

class ToposNode(BaseModel):
    """AST에서 추출된 단일 위상 노드"""
    fqn: str
    target_type: str  # 'function', 'class'
    role: str         # 'Implicit Node', 'Explicit Node', 'Hybrid Node'
    decorator_type: str
    contract: ContractSpec
    shape_hints: Dict[str, Any] = Field(default_factory=dict)
    positional_args: List[Any] = Field(default_factory=list)

class ToposProposal(BaseModel):
    """전체 시스템의 위상 제안 그룹"""
    groups: Dict[str, List[ToposNode]] = Field(default_factory=dict)