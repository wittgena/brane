# phase.runtime.cli.executor
## @lineage: phase.executor.cli
## @lineage: arch.executor.cli
import os
import sys
import uuid
import json
import asyncio
import argparse
import subprocess
import redis.asyncio as redis_async
from dataclasses import asdict
from typing import Callable, Any
from pathlib import Path
from arch.proto.event.psi import PsiEvent, PsiCarrier
from arch.proto.event.next import next_id, LogEvent
from phase.runtime.surface.sensor import REDIS_URL
from watcher.plane.emitter import get_emitter, flow_scope
from watcher.plane.surface import surface
from phase.bind.resolver import get_invoker
from arch.contract.registry.unified import registry
from phase.runtime.cli.task import TaskSummaryEvent, TaskDetailRecord
from arch.contract.base.executor import BaseExecutor

log = get_emitter("executor.cli")

def parse_local(argv):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--local", action="store_true")
    return parser.parse_known_args(argv)

def dispatch_cli(command_name: str, entry_func: Callable, file_path: str):
    """
    @role: Universal Execution Router
    @desc: CLI 자극(sys.argv)을 분석하여 물리적 로컬 실행을 할지, 위상 공간(Redis)으로 주입할지 결정합니다.
    """
    bound_args, remain = parse_local(sys.argv[1:])
    if bound_args.local:
        ## [ 차원 1: 물리적 직접 실행 ]
        log.info(f"[Router] Routing {command_name} to Local Process.")
        task = entry_func(remain)
        task.run() 
    else:
        ## [ 차원 2: 위상 공간으로의 사건(Ψ) 주입 ]
        log.info(f"[Router] Injecting {command_name} to Topological Manifold.")
        invoker, command = get_invoker(Path(file_path))
        payload = { "_context": {"invoker": str(invoker), "command": command, "cli_args": remain} }
        task = entry_func(remain)
        execute_cli_task(task_instance=task, command_name=command_name, payload=payload)

class _GenericCliExecutor(BaseExecutor):
    """bound(transduction) - external CLI → internal Ψ execution"""
    def __init__(self, task_instance, completion_signal: asyncio.Event):
        super().__init__()
        self.task_instance = task_instance
        self.completion_signal = completion_signal
        self.node = None

    async def execute(self, psi) -> list:
        command = psi.carrier.tag if hasattr(psi, 'carrier') else "CLI_TASK"
        task_id = getattr(psi, 'event_id', f"task-{next_id()}")

        detail_key = f"{command.lower()}:cli:{task_id}"
        latest_pointer_key = f"{command.lower()}:cli:latest"
        self.log.info(f"[exec] Executing CLI task: {command} ({task_id})")
        
        with flow_scope(flow_id=task_id, phase="EXECUTION"):
            self.log.info(f"[exec] Starting flow: {task_id}")
            try:
                ## 태스크 실행
                raw_result = self.task_instance.run() or {}
                # raw_result = await asyncio.to_thread(self.task_instance.run)
                # raw_result = raw_result or {}

                ## 결과 레코드 생성
                detail_record = TaskDetailRecord(
                    task_id=task_id,
                    command=command,
                    status=raw_result.get("status", "SUCCESS"),
                    artifacts=raw_result.get("artifacts", {}),
                    metrics=raw_result.get("metrics", {})
                )

                ## 요약 이벤트 생성
                summary_event = TaskSummaryEvent(
                    task_id=task_id,
                    command=command,
                    status=detail_record.status,
                    summary=raw_result.get("summary", f"Task {command} completed."),
                    detail_key=detail_key,
                    details=raw_result.get("details", {})
                )

                _project_to_stdout(summary_event)

                ## Redis 저장 및 공명(Reflection) 발행
                if self.node and self.node.redis:
                    await self.node.redis.set(detail_key, detail_record.to_json(), ex=3600)
                    await self.node.redis.set(latest_pointer_key, detail_key, ex=3600)
                    await asyncio.sleep(0.05)

                    response_channel = psi.context.get("response_channel")
                    if response_channel:
                        await self.node.redis.publish(response_channel, summary_event.to_json())
                        self.log.info(f"[exec] Reflection published to {response_channel}")
                    
                    self.log.info(f"[exec] Detailed artifacts saved -> Redis[{detail_key}]")

                ## 내부 버스용 결과 이벤트 발행
                result_carrier = PsiCarrier(kind="RESULT", tag=command, payload=asdict(summary_event))
                result_event = PsiEvent(
                    event_id=f"res-{task_id}",
                    parent_id=getattr(psi, 'event_id', None),
                    source_id="cli.executor",
                    scope="GLOBAL",
                    tick=1,
                    carrier=result_carrier
                )

                if self.node and getattr(self.node, 'bus', None):
                    await self.node.bus.publish(result_event)
            except Exception as e:
                self.log.error(f"[exec] Task Failed: {e}")
                import traceback; traceback.print_exc()
            finally:
                self.completion_signal.set()
        return []

def _project_to_stdout(summary_event: TaskSummaryEvent):
    """@topos.phase: Ψ → local surface projection (stdout)"""
    try:
        print(f"\n[{summary_event.status}] {summary_event.command}")
        print(f"{summary_event.summary}")
        print(f"detail_key: {summary_event.detail_key}")

        details = getattr(summary_event, "details", None)
        if isinstance(details, dict):
            print("\n## grouped result")
            for k, v in details.items():
                print(f"\n[{k}] ({len(v)})")
                for item in v[:5]:
                    print(f" - {item.get('namespace')}")

    except Exception:
        pass

class CliTaskAdapter:
    """순수 비즈니스 로직을 _GenericCliExecutor가 요구하는 표준 딕셔너리로 변환해주는 범용 어댑터"""
    def __init__(self, target_func: Callable, **kwargs):
        self.target_func = target_func
        self.kwargs = kwargs

    def run(self) -> dict:
        try:
            raw_result = self.target_func(**self.kwargs)
            if isinstance(raw_result, dict) and "status" in raw_result:
                return raw_result
                
            return {
                "status": "SUCCESS",
                "summary": "Task completed successfully.",
                "artifacts": [],
                "details": raw_result
            }
        except Exception as e:
            return {
                "status": "FAILED",
                "summary": f"Task failed: {str(e)}",
                "details": {"error": str(e)}
            }

async def _async_run_in_node(task_instance, command_name: str, payload: dict):
    r = redis_async.from_url(REDIS_URL, decode_responses=True)
    
    # -------------------------------------------------------------------------
    # [정밀 개선 구간] Live Check 및 스마트 스포닝 로직
    # -------------------------------------------------------------------------
    ## 1. 스웜의 실질적 가용성 정밀 파악
    # 모호한 'heartbeat' 키 대신, 실제 레지스트리에 등록된 'node'의 개수를 측정합니다.
    active_node_keys = await r.keys("runtime:node:*")
    node_count = len(active_node_keys)
    queue_len = await r.llen("runtime:queue")
    
    ## 2. 동적 부하율(Load Factor) 기반 스포닝 조건 판단
    MAX_LOAD_PER_NODE = 3  # 노드 1개당 감당할 큐의 최대 적체량
    is_overloaded = node_count > 0 and (queue_len / node_count) >= MAX_LOAD_PER_NODE
    
    should_spawn = (node_count == 0) or is_overloaded
    
    if should_spawn:
        ## 3. 분산 락(Distributed Lock)을 통한 '스폰 폭풍(Spawn Storm)' 방어
        # 여러 CLI가 0.1초 차이로 동시에 실행되어도 딱 1개의 프로세스만 노드를 스포닝하도록 10초짜리 락을 설정
        lock_acquired = await r.set("runtime:spawn_lock", "LOCKED", nx=True, ex=10)
        
        if lock_acquired:
            if node_count == 0:
                log.info("[CLI] No active nodes detected. Spawning background Ambient Node...")
            else:
                log.warn(f"[CLI] High load detected (Queue: {queue_len}, Nodes: {node_count}). Spawning additional Node...")
            
            ## 노드 프로세스 생성 (터미널 출력 차단, 데몬 형태 유지)
            subprocess.Popen(
                [sys.executable, "-m", "plane.node.runtime"],
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.DEVNULL,
                start_new_session=True,    
                env=os.environ.copy()      
            )
            
            ## 4. 확정적 부팅 대기 (Deterministic Boot Wait)
            # 노드가 실제로 부팅되어 레지스트리에 추가될 때까지 기다림
            for _ in range(15):  # 최대 7.5초 대기
                await asyncio.sleep(0.5)
                current_nodes = await r.keys("runtime:node:*")
                if len(current_nodes) > node_count:
                    break
        else:
            ## 이미 다른 프로세스가 노드를 띄우고 있다면 새로 띄우지 않고 대기
            log.info("[CLI] Another process is spawning a node. Waiting for boot sequence...")
            for _ in range(15):
                await asyncio.sleep(0.5)
                if not await r.exists("runtime:spawn_lock"):
                    break
    # -------------------------------------------------------------------------
    
    ## 결과 수신을 위한 채널 준비
    task_id = f"task-{uuid.uuid4().hex[:8]}"
    with flow_scope(flow_id=task_id, phase="CLI"):
        response_channel = f"res:{task_id}"
        log_channel = f"log:{task_id}"

        pubsub = r.pubsub()
        await pubsub.subscribe(response_channel, log_channel)
        log.info(f"[CLI] Listening on {response_channel} & {log_channel}...")

        ## 사건(Ψ) 주입 (노드에게 '레시피' 전달)
        trigger_event = PsiEvent(
            event_id=task_id,
            source_id=f"{command_name}:proxy",
            scope="GLOBAL",
            parent_id=None,
            tick=1,
            carrier=PsiCarrier(kind="COMMAND", tag=command_name.lower(), payload=payload),
            context={"response_channel": response_channel}
        )
        
        ## 큐에 사건을 밀어 넣음
        await r.lpush("runtime:queue", json.dumps(asdict(trigger_event)))

        try:
            ## 결과 대기 (노드가 작업을 완료하고 publish 할 때까지)
            async with asyncio.timeout(60):
                async for msg in pubsub.listen():
                    if msg["type"] != "message":
                        continue

                    channel = msg["channel"]
                    if channel == log_channel:
                        try:
                            log_data = json.loads(msg["data"])
                            
                            # [개선] 1. 자기 자신이 쏜 로그(Phase: CLI)는 화면에 다시 투영하지 않음
                            if log_data.get("context", {}).get("phase") == "CLI":
                                continue

                            # [개선] 2. LogEvent 필드에 없는 데이터가 들어와도 에러 나지 않게 필터링
                            from dataclasses import fields
                            valid_fields = {f.name for f in fields(LogEvent)}
                            clean_data = {k: v for k, v in log_data.items() if k in valid_fields}
                            
                            event = LogEvent(**clean_data)
                            surface.update(event)
                        except Exception:
                            continue 
                    elif channel == response_channel:
                        try:
                            data = json.loads(msg["data"])
                            print_formatted_result(data)
                            return 
                        except Exception as e:
                            log.error(f"[CLI] Failed to parse result data: {e}")
                            break 
        except TimeoutError:
            log.error(f"[CLI] Task timed out. Node failed to reflect within 60s.")
        finally:
            await pubsub.unsubscribe(response_channel)
            await r.close()

def execute_cli_task(task_instance, command_name: str = "run", payload: dict = None):
    """@topos.entry: external trigger → Ψ injection"""
    payload = payload or {}
    try:
        asyncio.run(_async_run_in_node(task_instance, command_name, payload))
    except KeyboardInterrupt:
        log.info("[CLI] Task interrupted by user.")

def print_formatted_result(data: dict):
    """전달받은 데이터(dict)를 기반으로 CLI에 리치 결과 출력"""
    status = data.get("status", "UNKNOWN")
    command = data.get("command", "task")
    summary = data.get("summary", "")
    details = data.get("details", {})
    detail_key = data.get("detail_key", "")

    ## 기본 헤더
    color_code = "\033[92m" if status == "SUCCESS" else "\033[91m"
    reset_code = "\033[0m"
    
    print(f"\n{color_code}[{status}]{reset_code} {command}")
    print(f"{summary}")

    ## 상세 정보(details)가 있을 경우 루프를 돌며 출력
    if isinstance(details, dict) and details:
        print("\n## Execution Details")
        for category, items in details.items():
            if isinstance(items, list):
                print(f"\n └─ [{category}] ({len(items)} items)")
                for item in items[:5]:
                    if isinstance(item, dict):
                        ns = item.get('namespace') or item.get('path') or str(item)
                        print(f"    - {ns}")
                if len(items) > 5:
                    print(f"    ... and {len(items)-5} more.")
            else:
                print(f" └─ {category}: {items}")

    print(f"\n(Full artifacts saved at Redis -> {detail_key})")