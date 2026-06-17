# arch.proto.phase.ator
import uuid
import asyncio
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Tuple
from watcher.plane.emitter import get_logger
from arch.proto.phase.flow import (
    PhaseFlow, FlowState, Dispersion, Judgment, 
    Transduction, Align, Resonance, Gather
)
from arch.contract.protocol import Proto, proto
from arch.contract.registry.unified import manifold_node, registry

log = get_logger('phase.ator')

class PhaseAtor:
    """
    @desc: Ator Adapters
    @invariant: 모든 하위 노드는 run(flow, operator, ctx) 시그니처를 따른다.
    """
    async def run(self, flow: PhaseFlow, operator: Any, ctx: FlowState) -> List[Tuple[str, FlowState]]:
        raise NotImplementedError()

@manifold_node(name="ator", requires=[], emits=["transduction"])
@proto(Proto((PhaseFlow, Transduction, "List[Tuple]"), kind="transduction"))
class TransAtor(PhaseAtor):
    def __init__(self, spec):
        self.role = spec["role"]
        self.next = spec["next"]
        self.node_context = spec.get("context", {})
        self.spec = spec

    async def run(self, flow: PhaseFlow, operator: Transduction, ctx: FlowState):
        log.info(f"    [TransAtor] '{self.role}' initiates self-transmutation")
        ## Context 주입 (Projection을 위한 준비)
        injected_state = {k: ctx.state.get(k) for k in self.node_context.get("inject_state", [])}
        flow.payload = {
            "raw_input": flow.payload,
            "instructions": self.node_context.get("instruction"),
            "injected_state": injected_state,
            "hyperparams": {"temperature": self.node_context.get("temperature", 0.7)}
        }

        ## Transduction 실행
        # 이 시점에서 operator.transduce 내의 projection이 수행되고, 
        # 마지막에 _close 내부의 kernel이 결합되며 ProtoFlow가 반환됨
        loop = asyncio.get_running_loop()
        new_flow = await loop.run_in_executor(None, operator.transduce, flow, self)
        ctx.flow = new_flow
        return [(self.next, ctx)]

@manifold_node(name="aligner", requires=[], emits=["aligner"])
@proto(Proto((PhaseFlow, Align, "State"), kind="aligner"))
class AlignAtor(PhaseAtor):
    def __init__(self, spec):
        self.next = spec["next"]
        self.spec = spec

    async def run(self, flow: PhaseFlow, operator: Align, ctx: FlowState):
        log.info(f"    [AlignAtor] reconcile ψ:{flow.id}")
        # ctx.state = operator.align(flow, ctx.state)
        result = operator.align(flow, self.spec)
        ctx.state.update(result.get("state", {}))
        flow.payload = result.get("payload", flow.payload)
        next_node = result.get("next", self.next)
        return [(self.next, ctx)]

@manifold_node(name="judgment", requires=[], emits=["judgment"])
@proto(Proto((PhaseFlow, Judgment, "str"), kind="judgment"))
class JudgmentAtor(PhaseAtor):
    def __init__(self, spec):
        self.rules = spec["rules"]
        op_name = spec.get("operator", "default_judgment")
        self.custom_op = registry.create_component("ator", {"type": op_name})

    async def run(self, flow: PhaseFlow, operator: Judgment, ctx: FlowState):
        ator = self.custom_op or base_operator
        target = ator.dispatch(flow, self.rules)
        log.info(f"    [JudgmentAtor] ψ:{flow.id} → {target}")
        return [(target, ctx)]

@manifold_node(name="dispersion", requires=[], emits=["dispersion"])
@proto(Proto((PhaseFlow, Dispersion, "List[ProtoFlow]"), kind="dispersion"))
class DispersionAtor(PhaseAtor):
    def __init__(self, spec):
        self.aspects = spec["aspects"]
        self.next = spec["next"]

    async def run(self, flow: PhaseFlow, operator: Dispersion, ctx: FlowState):
        log.info(f"    [DispersionAtor] scatter ψ:{flow.id}")
        flows = operator.scatter(flow, self.aspects)
        return [(self.next, FlowState(f, ctx.state)) for f in flows]

@manifold_node(name="gather", requires=[], emits=["gather"])
@proto(Proto((PhaseFlow, Gather, "List[ProtoFlow]"), kind="gather"))
class GatherAtor(PhaseAtor):
    """Operator 클래스로 분리했다고 가정하거나 기본 Operator를 만듬"""
    def __init__(self, spec):
        self.next = spec["next"]
        self.buffer = {}
        self.expected = spec.get("expected_count", 2)

    async def run(self, flow: PhaseFlow, operator: Gather, ctx: FlowState):
        root = flow.root
        slot = self.buffer.setdefault(root, [])
        slot.append(flow)

        log.info(f"    [GatherAtor] buffer ψ:{flow.id} {len(slot)}/{self.expected}")
        if len(slot) < self.expected:
            return []

        flows = self.buffer.pop(root)
        new_flow = operator.merge(flows, root)
        return [(self.next, FlowState(new_flow, ctx.state))]

@manifold_node(name="resonance", requires=[], emits=["resonance"])
@proto(Proto((PhaseFlow, Resonance, "ProtoFlow"), kind="resonance"))
class ResonanceAtor(PhaseAtor):
    def __init__(self, spec):
        self.next = spec["next"]
        self.buffer = {}
        op_name = spec.get("operator", "default_resonance")
        self.custom_op = registry.create_component("ator", {"type": op_name})

    async def run(self, flow: PhaseFlow, operator: Resonance, ctx: FlowState):
        root = flow.root
        tag = flow.aspect

        slot = self.buffer.setdefault(root, {})
        slot[tag] = flow.payload
        log.info(f"    [ResonanceAtor] interference update {tag}")
        if "code" not in slot or "logic" not in slot:
            return []

        data = self.buffer.pop(root)
        active_operator = self.custom_op or base_operator
        payload = active_operator.interfere(data["code"], data["logic"])
        new_flow = PhaseFlow(payload=payload, id=root, aspect="resonated", root=root)
        return [(self.next, FlowState(new_flow, ctx.state))]