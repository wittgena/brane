# arch.proto.phase.flow
"""
@phase
- ψ: event signal resonance around
- Φ: shared field state where tension accumulates
- ∂Φ: observers aligning drift and detecting rupture
- Σ: dispersion / aggregation of macro-micro flows

@flow: ψ → ator interaction → Φ drift → ∂Φ detection → rupture → new Φ regime
"""
import uuid
import enum
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Tuple
from watcher.plane.emitter import get_logger

log = get_logger("phase.flow")

class PhaseFlow:
    """
    @flow.model:
    - ψ: dynamic flow unit
    - Φ: shared state topology (memory/blackboard)
    """
    def __init__(self, payload=None, id=None, aspect=None, root=None):
        self.payload = payload
        self.id = id or str(uuid.uuid4())
        self.aspect = aspect or "default"
        self.root = root or self.id

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())[:6]

class FlowState:
    """coupling of ψ and Φ during runtime traversal"""
    def __init__(self, flow: PhaseFlow, state: Dict[str, Any]):
        self.flow = flow
        self.state = state

class Dispersion:
    """
    @flow: ψ → {ψ₁..ψₙ}
    @phase: dispersion / fan-out
    """
    def scatter(self, flow: PhaseFlow, aspects: List[str]) -> List[PhaseFlow]:
        log.info(f"  [Dispersion] '{flow.id}'를 {aspects}로 분화합니다.")
        return [PhaseFlow(payload=flow.payload, aspect=a, id=f"{flow.id}_{a}") for a in aspects]

class Judgment:
    """@flow: ψ → judgment → ψ_k"""
    def judge(self, flow: PhaseFlow, rules: List[Dict]) -> str:
        for rule in rules:
            cond = rule["if"]
            if "aspect" in cond and cond["aspect"] == flow.aspect:
                return rule["next"]
            if "contains" in cond and cond["contains"] in str(flow.payload):
                return rule["next"]
        return rules[-1]["next"]

class Transduction:
    """
    @flow: ψ_open → (project) → (close ⊕ kernel) → ψ_closed
    @desc: 상위 레벨에서의 폐합(Closure) 연산자
    """
    def transduce(self, flow: PhaseFlow, ator_node: Any) -> PhaseFlow:
        log.debug(f"## Current Instance Type: {type(self)}")
        projected_payload = self._project(flow, ator_node)
        return self._close(projected_payload, flow, ator_node)

    def _project(self, flow: PhaseFlow, ator_node: Any) -> dict:
        """기본형은 변화 없이(Identity) 페이로드를 반환"""
        return flow.payload

    def _close(self, projected, flow, ator_node):
        transformed = self._execute_transformation(
            projected,
            ator_node.node_context.get("instruction", "")
        )
        log.info(f"  [Closure] Binding kernel at the moment of closing ψ:{flow.id}")
        return PhaseFlow(
            payload=transformed,
            id=flow.id,
            aspect=f"transduced_{ator_node.role}",
            root=flow.root
        )

    def _execute_transformation(self, data, instruction):
        """커널 로직: 입력과 지침을 결합하여 실질적인 변화를 생성"""
        return f"Result({data} ⊕ {instruction})"

class Align:
    """
    @flow: ψ → ∂Φ → Φ'
    @phase: state alignment
    """
    def align(self, flow: PhaseFlow, state: Dict[str, Any]):
        log.info(f"  [Alignment] '{flow.aspect}' 결과를 상태 공간에 동기화합니다.")
        state[flow.id] = flow.payload
        return state

class Resonance:
    """
    @flow: ψ₁ ⊕ ψ₂ → ψ*
    @phase: resonance / interference
    """
    def interfere(self, a, b):
        return f"[Resonance] {a} ⊕ {b}"

class Gather:
    """
    @flow: {ψ₁..ψₙ} → gather → ψ_merged
    @phase: synchronization / fan-in
    """
    def merge(self, flows: List[PhaseFlow], root: str) -> PhaseFlow:
        """동일한 root를 가진 여러 ProtoFlow들을 하나로 병합 - 각 flow의 aspect를 key로 하여 payload를 딕셔너리 형태"""
        log.info(f"  [Gather] {len(flows)}개의 흐름을 하나로 병합 (root: {root})")
        
        ## 각 파편의 aspect(예: 'tech', 'market')를 키로 사용하여 페이로드 병합
        merged_payload = {f.aspect: f.payload for f in flows}
        return PhaseFlow(
            payload=merged_payload,
            id=root,
            aspect="merged",
            root=root
        )