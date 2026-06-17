# arch.topos.state.runtime
## @lineage: arch.topos.runtime
## @lineage: phase.topos.runtime
## @lineage: topos.state.runtime
import asyncio
import enum 
import logging
from typing import List, Tuple, Any, Optional, Dict
from dataclasses import field
from watcher.plane.emitter import get_emitter
from arch.contract.protocol import proto, get_proto, Proto
from arch.proto.phase.flow import PhaseFlow, FlowState
from arch.contract.state.spec import TransRule, NodeType
from arch.topos.node.state import LinkerNode, InversionNode, StateNode, ResidueType

log = get_emitter("state.runtime")

class StateRuntime:
    def __init__(self, entry: str, nodes: Dict[str, Any], runtime_node: Any):
        self.entry = entry
        self.nodes = nodes
        self.engine = runtime_node

        self.psi_queue = asyncio.Queue()
        self._tasks: List[asyncio.Task] = []
        self._is_active = False
        self.flow_completed = asyncio.Event()

    async def _process_queue_loop(self):
        step = 0
        log.info("[ToposRuntime] Attached. Waiting for signals...")
        
        ## 자체 활성 플래그와 엔진의 running 상태를 모두 체크
        while self._is_active and getattr(self.engine, 'running', True):
            try:
                ## 큐 대기 중 취소(Cancelled)될 수 있으므로 분리
                node_name, ctx = await self.psi_queue.get()
                step += 1

                try:
                    if node_name == "END":
                        log.info(f"[Step {step}] Terminal reached. Flow Ended.")
                        log.info(f"Final Residues: {ctx.state.get('residues')}")
                        self.flow_completed.set()
                        continue

                    log.info(f"[Step {step}] Executing Node: {node_name}")
                    node = self.nodes[node_name]
                    node_cls = node.__class__

                    p = get_proto(node_cls)
                    if not p:
                        raise RuntimeError(f"[{node_name}] Missing @proto metadata.")

                    if ctx.state.get("__reentry__"):
                        ctx.state.pop("__reentry__", None)
                        await self.psi_queue.put((self.entry, ctx))
                        continue

                    operator_type = p.sequence[1]
                    operator = operator_type() 
                    next_steps = await node.run(ctx.flow, operator, ctx)
                    for nxt_node, nxt_ctx in next_steps:
                        await self.psi_queue.put((nxt_node, nxt_ctx))
                finally:
                    self.psi_queue.task_done()

            except asyncio.CancelledError:
                log.info("[ToposRuntime] Process loop cancelled.")
                break
            except Exception as e:
                log.error(f"Error: {e}", exc_info=True)

    def attach(self):
        """런타임 루프를 구동하고 태스크를 내부적으로 추적"""
        self._is_active = True
        controller_task = asyncio.create_task(self._process_queue_loop())
        controller_task.set_name(f"ToposRuntime-Loop-{id(self)}")
        self._tasks.append(controller_task)
        log.debug(f"[ToposRuntime] Attached successfully. Tracking {len(self._tasks)} tasks.")

    async def detach(self):
        """ToposRuntime 전용의 우아한 종료(Graceful Teardown) 시퀀스"""
        if not self._is_active:
            return
            
        log.info("[ToposRuntime] Detach sequence initiated...")
        self._is_active = False
        
        for task in self._tasks:
            if not task.done():
                task.cancel()
        
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        log.info("[ToposRuntime] Detached and all internal tasks cleared.")