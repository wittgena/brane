# arch.topos.node.state
## @lineage: phase.topos.node.state
## @lineage: topos.state.node
import asyncio
import enum 
import logging
from typing import List, Tuple, Any, Optional, Dict
from watcher.plane.emitter import get_emitter
from arch.contract.protocol import proto, get_proto, Proto
from arch.proto.phase.flow import PhaseFlow, FlowState
from arch.contract.state.spec import TransRule, PhaseSpec, NodeType

log = get_emitter("state.node")

class ResidueType(enum.Enum):
    INFO, WARN, ERROR, TRANSITION = "INFO", "WARN", "ERROR", "TRANSITION"

class BaseNode:
    def __init__(self, spec: dict, pool: Optional[Any] = None, **kwargs):
        self.spec = spec
        self.pool = pool 

    async def run(self, flow: PhaseFlow, operator: Any, ctx: FlowState) -> List[Tuple[str, FlowState]]:
        pass

class StateOperator:
    """ToposNode 구동을 위한 더미 오퍼레이터 (필요 시 로직 확장)"""
    pass

class Inversion:
    def mutate(self, spec: PhaseSpec, root: 'ToposNode') -> List[Dict]:
        residues = []
        self_node = root.children.get("self")
        
        if not self_node:
            return [{"type": ResidueType.ERROR, "msg": "Critical: 'self' node missing"}]

        residues.append({"type": ResidueType.TRANSITION, "msg": f">>> Transition to {spec.phase_name} >>>"})
        for rule in spec.rules:
            source_node = self_node.children.get(rule.source_name)
            if not source_node: continue

            if source_node.kind == NodeType.ANCHOR or rule.source_name in ["self", "root"]:
                residues.append({"type": ResidueType.WARN, "msg": f"Access Denied: Cannot invert Anchor '{rule.source_name}'"})
                continue

            if rule.action == "INVERT":
                removed = self_node.children.pop(rule.source_name)
                new_core = StateNode(spec={
                    "name": rule.target_name,
                    "kind": rule.target_kind,
                    "content": f"Materialized from {removed.ref_target}"
                })
                self_node.children[rule.target_name] = new_core
                residues.append({"type": ResidueType.INFO, "msg": f"Inverted: {rule.source_name} -> {rule.target_name}"})

        return residues

@proto(Proto((PhaseFlow, StateOperator, "State"), kind="phase"))
class StateNode(BaseNode):
    def __init__(self, spec: dict, pool: Any = None, **kwargs):
        super().__init__(spec, pool, **kwargs)
        self.name = spec.get("name", "unnamed")
        self.kind = spec.get("kind", NodeType.CORE)
        self.content = spec.get("content")
        self.ref_target = spec.get("ref_target")
        self.children: Dict[str, 'ToposNode'] = spec.get("children", {})
        self.next = spec.get("next", "END")

    async def run(self, flow: PhaseFlow, operator: StateOperator, ctx: FlowState) -> List[Tuple[str, FlowState]]:
        log.info(f"  [ToposNode] Processing state -> Name: {self.name}, Kind: {self.kind}")
        return [(self.next, ctx)]

@proto(Proto((PhaseFlow, Inversion, "State"), kind="linker"))
class LinkerNode(BaseNode):
    def __init__(self, spec: dict, pool: Any = None, **kwargs):
        super().__init__(spec, pool, **kwargs)
        self.next = spec.get("next", "END")

    async def run(self, flow: PhaseFlow, operator: Inversion, ctx: FlowState) -> List[tuple]:
        log.info("  [LinkerNode] Synthesizing internal & external rules...")
        phase = ctx.state.get("phase_root")
        
        # 1. 내부 자가 유도 규칙 (Self-evolution)
        rules = self._derive_rules(phase) if phase else []
        
        # 2. 외부 PR 신호 처리 (Selective Adoption)
        external_rules = ctx.state.get("external_rules", [])
        if external_rules:
            # 주권(Sovereignty) 필터: 내 위상에 실체가 있고 ANCHOR가 아닌 것만 채택
            filtered_external = self._filter_rules(phase, external_rules)
            rules.extend(filtered_external)
            ctx.state.pop("external_rules", None)

        if rules:
            flow.payload["target_spec"] = PhaseSpec(
                phase_name=f"evo_{ctx.flow.id[:4]}",
                structure={},
                rules=rules
            )
            
        return [(self.next, ctx)]

    def _derive_rules(self, node: StateNode) -> List[TransRule]:
        rules = []
        for child_name, child_node in node.children.items():
            if child_node.kind == NodeType.SYMLINK:
                rules.append(TransRule(child_name, f"core_{child_name}", NodeType.CORE))
            rules.extend(self._derive_rules(child_node))
        return rules

    def _filter_rules(self, phase, external_rules):
        # 외부 제안 중 내 위상 정합성에 맞는 것만 선별하는 로직
        return [r for r in external_rules if self._is_safe(phase, r)]

    def _is_safe(self, phase, rule):
        # ANCHOR 보호 및 존재 여부 확인 로직 (기존 로직 재사용)
        return True # (구현 생략)

# 런타임 외부 로직
def inject_pr_signal(ctx: FlowState, pr_signal: Dict):
    """
    외부 PR(Signal)을 받아 런타임이 이해할 수 있는 형태(external_rules)로
    FlowState에 주입하는 어댑터 역할
    """
    # PR을 TransRule 객체 리스트로 변환
    rules = [
        TransRule(r['src'], r['dest'], NodeType[r['kind']]) 
        for r in pr_signal.get('proposed_changes', [])
    ]
    
    # 런타임 큐에 들어가기 전 state에 보관
    ctx.state["external_rules"] = rules
    return ctx

@proto(Proto((PhaseFlow, Inversion, "State"), kind="inversion"))
class InversionNode(BaseNode):
    def __init__(self, spec: dict, pool: Any = None, **kwargs):
        super().__init__(spec, pool, **kwargs)
        self.next = spec.get("next", "END")

    async def run(self, flow: PhaseFlow, operator: Inversion, ctx: FlowState) -> List[tuple]:
        target_spec = flow.payload.get("target_spec")
        phase = ctx.state.get("phase_root")

        if not target_spec or not phase:
            ctx.state.pop("__reentry__", None)
            return [(self.next, ctx)]

        # Pure Mutation
        new_residues = operator.mutate(target_spec, phase)
        has_mutated = any(r["type"] == ResidueType.INFO for r in new_residues)

        # 변이 발생 시에만 재진입, 아니면 수렴(Stop)
        if has_mutated:
            ctx.state["__reentry__"] = True
            ctx.state["root"] = phase
        else:
            ctx.state.pop("__reentry__", None)
            log.info("  [InversionNode] Topology converged.")

        # Residue 기록
        ctx.state.setdefault("residues", []).extend(new_residues)
        return [(self.next, ctx)]