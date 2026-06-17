# phase.ator.runtime
## @lineage: phase.hub.ator.runtime
## @lineage: hub.ator.runtime
## @lineage: xe.ator.runtime
## @lineage: xphi.ator.runtime
## @lineage: cognitive.xphi.ator.runtime
## @lineage: topos.bound.ator.runtime
import asyncio
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Tuple
from watcher.plane.emitter import get_logger
from arch.proto.phase.flow import PhaseFlow, FlowState
from arch.contract.protocol import get_proto
from arch.proto.event.psi import PhaseField, PsiCarrier, CarrierType
from arch.contract.state.node0 import enter_node0
from phase.runtime.node import NodeRuntime
from phase.runtime.interpreter import AnchorFlow, NodeInterpreter

log = get_logger("ator.runtime")

class AtorRuntime:
    """
    @role: Φ-field mediator
    @flow: Ψ → Φ' → ∂Φ → Node0 → Ψ' → Φ'
    @semantics:
    - PIR = Φ' (judgment operator)
    - boundary = ∂Φ (phase discontinuity)
    - Node0 = transducer (∂Φ → Ψ')
    """
    def __init__(self, entry: str, nodes: Dict[str, Any], runtime_node: NodeRuntime):
        self.entry = entry
        self.nodes = nodes
        self.engine = runtime_node
        
        self.psi_queue = asyncio.Queue()
        self._tasks: List[asyncio.Task] = []
        self._is_active = False
        
        ## Φ₀: global anchor (phase origin)
        self.global_anchor = AnchorFlow.bootstrap()
        
        ## Φ'-operators per local field
        self.interpreters = self._initialize_interpreters()

        ## τ: minimal boundary threshold
        self.boundary_threshold = 0.5
        log.info(f"[RuntimeAtor] Initialized with Anchor Version: {self.global_anchor.version}")

    def _initialize_interpreters(self) -> Dict[str, NodeInterpreter]:
        return {
            "ator": NodeInterpreter(self.global_anchor, field=PhaseField.COHERENT),
            "router": NodeInterpreter(self.global_anchor, field=PhaseField.EVALUATION),
            "resonance": NodeInterpreter(self.global_anchor, field=PhaseField.INTERFERENCE),
            "default": NodeInterpreter(self.global_anchor)
        }

    def _flow_to_carrier(self, flow: PhaseFlow, node_type: str) -> PsiCarrier:
        field_map = {
            "ator": PhaseField.COHERENT,
            "router": PhaseField.EVALUATION,
            "resonance": PhaseField.INTERFERENCE
        }
        payload_data = flow.payload.get("status", "psi:ok") if isinstance(flow.payload, dict) else str(flow.payload)
        
        return PsiCarrier(
            kind="status", tag="status", payload=payload_data,
            target_field=field_map.get(node_type, PhaseField.COHERENT),
            carrier_type=CarrierType.RECURSIVE,
        )

    def _sync_interpreters(self):
        for interp in self.interpreters.values():
            interp.anchor = self.global_anchor

    def _route_to_boundary(self, ctx):
        return [("NODE0", ctx)]

    async def _process_queue_loop(self):
        step = 0
        log.info("[RuntimeAtor] Attached to Local Queue. Waiting for Ψ injection...")
        
        # [개선 2] 엔진의 상태와 자신의 활성 상태를 모두 체크
        while self._is_active and getattr(self.engine, 'running', True):
            try:
                item = await self.psi_queue.get()
                step += 1

                if isinstance(item, tuple) and len(item) == 2:
                    node_name, ctx = item
                else:
                    log.debug(f"[Step {step}] Topology mismatch: Ignored non-Ator carrier type {type(item)}")
                    self.psi_queue.task_done()
                    continue

                if not hasattr(ctx, "state") or ctx.state is None:
                    ctx.state = {}

                if node_name == "UGA":
                    log.info(f"[Step {step}] Closure Reached. Final State: {ctx.state}")
                    self.psi_queue.task_done()
                    continue

                if node_name == "NODE0":
                    log.warning(f"[Step {step}] Entering Node0 boundary context")
                    interp = self.interpreters["default"]
                    with enter_node0(interp, "runtime") as n0:
                        if isinstance(ctx.flow.payload, dict):
                            ctx.flow.payload["status"] = "psi:recovered"

                    ctx.state.pop("boundary", None)
                    await self.psi_queue.put((self.entry, ctx))
                    self.psi_queue.task_done()
                    continue

                node = self.nodes.get(node_name)
                if not node:
                    log.error(f"[Step {step}] Node '{node_name}' not found in manifold.")
                    self.psi_queue.task_done()
                    continue

                node_cls = node.__class__
                p = get_proto(node_cls)
                if not p:
                    raise RuntimeError(f"[{node_name}] Missing @proto metadata.")

                node_type = getattr(p, "kind", "default")
                interp = self.interpreters.get(node_type, self.interpreters["default"])
                carrier = self._flow_to_carrier(ctx.flow, node_type)
                
                interp.process(carrier)
                current_anchor = interp.anchor

                if current_anchor.version > self.global_anchor.version:
                    log.warning(f"[Step {step}] Singularity detected")
                    # [버그 수정] new_anchor가 아닌 current_anchor로 동기화
                    self.global_anchor = current_anchor 
                    self._sync_interpreters()
                    ctx.state["boundary"] = "inversion"
                    if isinstance(ctx.flow.payload, dict):
                        ctx.flow.payload["status"] = "delta:resolved"

                if ctx.state.get("boundary"):
                    log.warning(f"[Step {step}] Topology fractured. Bypassing F_op and routing to NODE0.")
                    next_steps = self._route_to_boundary(ctx)
                else:
                    log.info(f"[Step {step}] Executing F_op on Node: {node_name}")
                    if hasattr(node, "bound_operator") and node.bound_operator is not None:
                        operator = node.bound_operator
                        log.info(f"  [DI] Injecting dynamic operator: {type(operator).__name__}")
                    else:
                        operator_type = p.sequence[1]
                        operator = operator_type()
                        log.info(f"  [DI] Injecting fallback operator: {type(operator).__name__}")

                    next_steps = await node.run(ctx.flow, operator, ctx)
                
                controlled_steps = self._control_flow(next_steps, ctx, node_name)
                for nxt_node, nxt_ctx in controlled_steps:
                    await self.psi_queue.put((nxt_node, nxt_ctx))

                self.psi_queue.task_done()
            except asyncio.CancelledError:
                log.info("[RuntimeAtor] Process loop cancelled.")
                break
            except Exception as e:
                log.error(f"Error during node execution: {e}", exc_info=True)
                self.psi_queue.task_done()

    def _control_flow(self, next_steps, ctx, current_node_name: str):
        controlled = []
        current_node = self.nodes.get(current_node_name)
        flow_rules = getattr(current_node, "spec", {}).get("flow", {}) if current_node else {}
        for nxt_node, nxt_ctx in next_steps:
            if nxt_node == "END":
                controlled.append((nxt_node, nxt_ctx))
                continue
            if getattr(nxt_ctx, "state", {}).get("halt"):
                continue
                
            # [개선 3] 엔진 큐가 아닌 로컬 큐 압력 확인
            if self.psi_queue.qsize() > 1000:
                log.warning("Backpressure triggered, dropping flow")
                continue

            if nxt_ctx.state.get("boundary"):
                log.warning(f"[Boundary] Routing to Node0: {nxt_node}")
                on_fracture_target = flow_rules.get("on_fracture")
                if on_fracture_target:
                    log.warning(f"[Boundary] Fracture intercepted by @flow rule. Routing to: {on_fracture_target}")
                    nxt_ctx.state.pop("boundary", None) 
                    return [(on_fracture_target, nxt_ctx)]
                else:
                    log.warning(f"[Boundary] No fracture rule. Routing to Node0: {nxt_node}")
                    return self._route_to_boundary(nxt_ctx)

            controlled.append((nxt_node, nxt_ctx))
        return controlled

    def attach(self):
        """[개선 4] 독립적인 생명주기 스레드 추적"""
        self._is_active = True
        controller_task = asyncio.create_task(self._process_queue_loop())
        controller_task.set_name(f"AtorRuntime-Loop-{id(self)}")
        self._tasks.append(controller_task)
        log.debug(f"[RuntimeAtor] Attached successfully. Tracking {len(self._tasks)} tasks.")

    async def detach(self):
        """[개선 5] 잔여 태스크 소멸 및 우아한 종료 시퀀스"""
        if not self._is_active:
            return
        log.info("[RuntimeAtor] Detach sequence initiated...")
        self._is_active = False
        
        for task in self._tasks:
            if not task.done():
                task.cancel()
        
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        log.info("[RuntimeAtor] Detached and all internal tasks cleared.")