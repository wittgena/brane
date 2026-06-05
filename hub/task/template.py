# meta.debug.task.template
## @lineage: agent.manager.task.template
from typing import TypedDict, List, Dict, Any, Optional
from dataclasses import dataclass, asdict, field

# ==========================================
# 1. Edge & Relation Models (연결 및 사유 궤적)
# ==========================================
class EdgeData(TypedDict):
    """에이전트 간의 작업 흐름 및 사유 궤적 (Task Pipeline & CoT Rationale)"""
    source: str
    target: str
    keyword: str              # "coupled", "flows_into", "blocks" 등 관계 타입
    rationale: str            # [NEW] ThCh CoT에서 추출된 연결 근거 (왜 이 타겟을 호출했는가)
    confidence: float         # [NEW] LLM이 이 엣지를 생성할 때의 확신도 (0.0 ~ 1.0)
    linenos: List[int]        # (Legacy 호환성) 구문 분석 기반일 경우 사용

class LoopEdgeData(TypedDict):
    source: str
    target: str
    type: str

@dataclass
class NodeRelation:
    """런타임 위상에서 노드 간의 동적 결합 상태"""
    target: str
    rel: str = "coupled"
    strength: int = 1
    rationale: str = ""       # 런타임에 동적으로 주입되는 사유

# ==========================================
# 2. Node & Topology Models (에이전트 위상 상태)
# ==========================================
class NodeData(TypedDict):
    """개별 에이전트/Task의 상태 및 인지적 성숙도 (Metabolic Node)"""
    id: str
    file_path: str
    layer: str                 # L0(Worker) ~ L4(Orchestrator) 에이전트 페르소나
    is_topos: bool             # 자체 피드백 루프(자가 치유) 존재 여부
    degree: int
    betweenness: float
    signature_ref: str         # 바인딩된 ProtoSignature 이름 (계약)
    is_hydrated: bool          # ThCh 상태(최적화 가중치) 로드(복원) 여부
    optimization_epoch: int    # 이 에이전트가 경험한 옵티마이저 컴파일 횟수
    failure_rate: float        # CoT 추론 과정 중 파싱 에러 및 구조화 실패 비율

@dataclass
class ResonanceNode:
    """매니폴드 내의 단일 런타임 위상 노드"""
    id: str
    intensity: int             # 엔트로피, 혼란도 (0~100)
    is_invariant: bool         # 절대 제약(Zero-UI 철학 등) 위반 여부
    boundaries: Dict[str, int]
    support_manifold: List[str]
    relations: List[NodeRelation] = field(default_factory=list)

# ==========================================
# 3. Graph & Meta Models (시스템 전체 면역 및 관측)
# ==========================================
class MetaModel(TypedDict):
    """시스템 전체 관측 및 자가 치유 트리거 지표 (Immune/Validator Node)"""
    total_modules: int
    total_dependencies: int
    cycles_detected: int       # 에이전트 간 데드락 발생 횟수
    layer_distribution: Dict[str, int]
    absorbable_count: int      
    phase_stability: float     # 위상 안정성 점수 (100점 만점)
    # [NEW] 자가 치유(Autopoietic Healing) 지표
    entropy_delta: float       # 최근 N사이클 동안의 위상 안정성 증감률 (음수면 붕괴 중)
    recompile_required: bool   # 안정성 임계점 미만으로 ThCh Optimizer 가동이 필요한 상태인가?
    target_nodes_to_heal: List[str] # 에러율(failure_rate)이 높아 재학습이 필요한 노드 ID 목록

@dataclass
class GraphSchema:
    """전체 시스템의 동적 위상 지도 (Model Manifold Projection)"""
    meta: MetaModel
    nodes: List[NodeData]
    topos_edges: List[EdgeData]
    loop_edges: List[LoopEdgeData]
    cycles: List[List[str]]
    invariants: List[str] = field(default_factory=list)  # Resonance 통합
    version: str = "3.0"                                 # Evolutionary Phase 적용
    type: str = "topos.network.agentic"

    def to_dict(self) -> dict:
        return asdict(self)

# ==========================================
# 4. Contextual Boundary Projection (관측 시야 제한)
# ==========================================
@dataclass
class BridgeEvent:
    """엔진에 상관없이 워크플로우가 수신할 공통 이벤트 규격"""
    content: str
    source: str = "agent"
    event_type: str = "message"

@dataclass
class EntryNode:
    entry: str
    focus: str = "CLI Observation"
    depth: int = 1
    relations: List[str] = field(default_factory=lambda: ["coupled", "flows_into"])

    @property
    def valid_relations(self) -> set:
        return set(self.relations)

@dataclass
class RenderingData:
    """마크다운 렌더링에 주입되는 템플릿 데이터 모델"""
    entry_point: str
    focus: str
    depth: str
    relations_list: str
    fragments: str
    relations: str

def _extract_rel_attr(rel: Any, key: str, default: Any = None) -> Any:
    """dict 또는 객체 형태의 relation에서 속성을 안전하게 추출"""
    if isinstance(rel, dict):
        return rel.get(key, default)
    return getattr(rel, key, default)

class EntryTemplate:
    MARKDOWN = """# Entry: {entry_point}

> **Phase**: Φ′ → Ψ (Contextual Subgraph) → Φs
> **Role**: Dynamic Perspective Projection

## @focus.context
- **Focus**: `{focus}`
- **Depth**: {depth}
- **Relations**: {relations_list}

---

## @local.topology (Selected Fragments)
{fragments}

---

## @expansion (Paths)
{relations}

---
*Projected via `EntryProjector` (Dynamic Boundary)*
"""