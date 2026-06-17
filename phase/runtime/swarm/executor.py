# phase.runtime.swarm.executor
import os
import sys
import uuid
import json
import asyncio
import subprocess
import importlib
from typing import Callable, Any
from arch.proto.event.psi import PsiEvent, PsiCarrier
from arch.proto.event.next import next_id, LogEvent
from dataclasses import asdict
from watcher.plane.surface import surface
from watcher.plane.emitter import get_logger, flow_scope
from arch.contract.registry.unified import registry
from arch.contract.base.executor import BaseExecutor
from phase.runtime.cli.executor import _GenericCliExecutor
from phase.dynamics.flow.executor import _FlowExecutor

log = get_logger("swarm.executor")

class SwarmExecutor(BaseExecutor):
    """특정 인스턴스가 아닌, 레지스트리에서 태스크를 동적으로 찾아 실행하는 스웜용 실행기"""
    
    def __init__(self, completion_signal: asyncio.Event):
        super().__init__()
        self.completion_signal = completion_signal
        self.node = None

    async def execute(self, psi: PsiEvent) -> list:
        if not hasattr(psi, 'carrier') or psi.carrier.kind != "COMMAND":
            return []

        context = psi.carrier.payload.get("_context", {})
        command = context.get("command") or psi.carrier.tag
        cli_args = context.get("cli_args", [])
        task_id = getattr(psi, 'event_id', None) or f"task-{next_id()}"

        if not command: 
            self.log.error(f"[Swarm] Cannot resolve command from payload or tag. (Event ID: {task_id})")
            return []

        ## 레지스트리에서 해당 커맨드에 매핑된 모듈/함수 정보 획득
        task_info_list = registry.registered_cli_tasks.get(command)
        if not task_info_list: 
            self.log.error(f"[Swarm] No registered task found for: {command}")
            return []

        with flow_scope(flow_id=task_id, phase="EXECUTION"):
            self.log.info(f"[SwarmCliExecutor] flow_id: {task_id}")
            
            try:
                task_info = task_info_list[0]
                module_fqn = task_info.get("module_fqn")
                entry_func_name = task_info.get("entry", "entry_task")
                task_type = task_info.get("type", "cli") 
                
                ## 모듈 동적 임포트
                module = importlib.import_module(module_fqn)
                if not hasattr(module, entry_func_name):
                    self.log.error(f"[Swarm] '{entry_func_name}' not found in {module.__name__}")
                    return []

                ## 진입점 함수 추출 및 태스크 인스턴스 생성
                entry_func = getattr(module, entry_func_name)
                task_instance = entry_func(cli_args)
                
                ## 내부 실행기를 위한 독립적인 완료 시그널 생성
                sub_completion_signal = asyncio.Event()
                
                if task_type == "flow":
                    internal_executor = _FlowExecutor(task_instance, sub_completion_signal)
                    self.log.info(f"[Swarm] Allocated _FlowExecutor for {command}")
                else:
                    internal_executor = _GenericCliExecutor(task_instance, sub_completion_signal)
                    self.log.info(f"[Swarm] Allocated _GenericCliExecutor for {command}")

                if self.node:
                    internal_executor.node = self.node
                else:
                    self.log.warn("[Swarm] Executor has no node reference! Reflection might fail.")
                
                ## 내부 Executor(GenericCliExecutor)에 실행 위임
                await internal_executor.execute(psi)
            except Exception as e:
                self.log.error(f"[Swarm] Execution Failed: {e}")
                import traceback; traceback.print_exc()
            finally:
                self.completion_signal.set()
                
        return []