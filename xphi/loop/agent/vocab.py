# xphi.loop.agent.vocab
## @lineage: bound.agent.loop.vocab
from enum import Enum

class NodeType(str, Enum):
    """IR(중간 표현체) 단계에서의 논리적 노드 역할"""
    PROJECTOR = "projector"
    OPERSIG = "opersig"
    ACT = "act"
    PENDING = "pending"
    REFLECT = "reflect"
    TENSION = "tension"

class SigType(str, Enum):
    """DagOrganizer가 인식하는 런타임 물리 핸들러 타입"""
    PROJECTOR = "signature.projector"
    OPERSIG = "signature.opersig"
    ACT = "signature.act"
    PENDING = "signature.pending"
    REFLECT = "signature.reflect"
    TENSION = "signature.tension"
    ROUTER = "signature.router"
    END = "END"

class EdgeMode(str, Enum):
    """노드 간 전이(Transition) 방식"""
    DIRECT = "direct"
    CONDITIONAL = "conditional"
    FALLBACK = "fallback"

class SpecKey:
    """Runtime JSON Spec에서 사용되는 표준 키 값들"""
    TYPE = "type"
    NEXT = "next"
    FALLBACK = "fallback"
    ATTRIBUTES = "attributes"
    MAX_FAILURES = "max_failures"
    RULES = "rules"
    DEFAULT_NEXT = "default_next"
    IF_COND = "if"
    ASPECT = "aspect"

# 기본 매핑 레지스트리
DEFAULT_TYPE_MAP = {
    NodeType.PROJECTOR: SigType.PROJECTOR,
    NodeType.OPERSIG: SigType.OPERSIG,
    NodeType.ACT: SigType.ACT,
    NodeType.PENDING: SigType.PENDING,
    NodeType.REFLECT: SigType.REFLECT,
    NodeType.TENSION: SigType.TENSION,
}