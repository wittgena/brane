# phase.dynamics.flow.executor
## @lineage: arch.dynamics.flow.executor
## @lineage: arch.flow.executor
## @lineage: cognitive.flow.executor
## @lineage: phase.executor.flow
## @lineage: arch.executor.flow
import os
import sys
import uuid
import json
import asyncio
import argparse
import subprocess
import redis.asyncio as redis_async
from typing import Callable, Any, AsyncGenerator
from pathlib import Path
from dataclasses import asdict
from arch.proto.event.psi import PsiEvent, PsiCarrier
from arch.proto.event.next import next_id, LogEvent
from phase.runtime.surface.sensor import REDIS_URL
from watcher.plane.emitter import get_emitter, flow_scope
from watcher.plane.surface import surface
from phase.bind.resolver import get_invoker
from arch.contract.base.executor import BaseExecutor

log = get_emitter("executor.flow")

def parse_local(argv):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--local", action="store_true")
    return parser.parse_known_args(argv)

def dispatch_flow_cli(command_name: str, entry_func: Callable, file_path: str):
    """
    @role: Universal Flow Router
    @desc: CLI 자극을 분석하여 물리적 로컬 스트리밍을 할지, Node(위상 공간)에 주입하여 원격 스트리밍을 받을지 결정.
    """
    bound_args, remain = parse_local(sys.argv[1:])
    
    # entry_func는 RMFlow와 같이 async for로 순회 가능한 객체를 반환해야 함
    flow_instance = entry_func(remain)
    
    if bound_args.local:
        ## [ 차원 1: 물리적 직접 실행 (Local Stream) ]
        log.info(f"[Router] Routing {command_name} to Local Process Stream.")
        asyncio.run(_local_stream_runner(flow_instance, command_name))
    else:
        ## [ 차원 2: 위상 공간으로의 사건(Ψ) 주입 (Remote Stream) ]
        log.info(f"[Router] Injecting {command_name} Flow to Topological Manifold.")
        invoker, command = get_invoker(Path(file_path))
        payload = { "_context": {"invoker": str(invoker), "command": command, "cli_args": remain} }
        
        execute_flow_cli_task(flow_instance=flow_instance, command_name=command_name, payload=payload)


async def _local_stream_runner(flow_instance, command_name):
    """로컬 실행 시 Redis를 거치지 않고 터미널에 직접 투영"""
    print(f"\n[\033[94mLOCAL STREAM\033[0m] Starting {command_name}...")
    async for event in flow_instance.execute():
        event_type = type(event).__name__
        if event_type == "FlowEvent":
            print(f" ├─ [FLOW:{event.phase}] {event.psi.name} -> {event.phi.name} (Bound: {event.boundary.name})")
        elif event_type == "CollapseEvent":
            print(f" └─ [\033[92mCOLLAPSE\033[0m] Converged to '{event.surface.name}'")

class _FlowExecutor(BaseExecutor):
    """bound(transduction) - external CLI → internal continuous Ψ stream execution"""
    
    def __init__(self, flow_instance, completion_signal: asyncio.Event):
        super().__init__()
        self.flow_instance = flow_instance
        self.completion_signal = completion_signal
        self.node = None

    async def execute(self, psi) -> list:
        command = getattr(psi.carrier, 'tag', "FLOW_TASK")
        task_id = getattr(psi, 'event_id', f"flow-{next_id()}")
        response_channel = psi.context.get("response_channel")
        
        detail_key = f"{command.lower()}:flow:{task_id}"
        events_history = []

        self.log.info(f"[exec] Executing Flow task: {command} ({task_id})")

        with flow_scope(flow_id=task_id, phase="EXECUTION"):
            try:
                # 1. RMFlow 스트림 비동기 순회
                async for event in self.flow_instance.execute():
                    event_type = type(event).__name__
                    events_history.append(event)
                    
                    if not (self.node and response_channel):
                        continue
                        
                    # 2. 중간 FlowEvent는 실시간으로 클라이언트에 중계
                    if event_type == "FlowEvent":
                        stream_payload = {
                            "type": "FLOW",
                            "phase": event.phase,
                            "psi": event.psi.name,
                            "phi": event.phi.name,
                            "bound": event.boundary.name
                        }
                        await self.node.redis.publish(response_channel, json.dumps(stream_payload))
                    
                    # 3. CollapseEvent (종결) 도달 시 최종 저장 및 종료 신호
                    elif event_type == "CollapseEvent":
                        summary_payload = {
                            "type": "COLLAPSE",
                            "status": "SUCCESS",
                            "command": command,
                            "summary": f"System converged to '{event.surface.name}'",
                            "detail_key": detail_key,
                            "details": {"history_length": len(events_history), "final_surface": event.surface.name}
                        }
                        
                        # Node의 Redis에 최종 상태 저장
                        await self.node.redis.set(detail_key, json.dumps(summary_payload), ex=3600)
                        
                        # 발화자(CLI Proxy)에게 최종 이벤트 퍼블리시
                        await self.node.redis.publish(response_channel, json.dumps(summary_payload))
                        self.log.info(f"[exec] Flow Collapsed. Saved -> Redis[{detail_key}]")
                        
                        # 내부 버스 이벤트 (다른 노드들과의 공명용)
                        if getattr(self.node, 'bus', None):
                            result_event = PsiEvent(
                                event_id=f"res-{task_id}",
                                parent_id=getattr(psi, 'event_id', None),
                                source_id="flow.executor",
                                scope="GLOBAL",
                                tick=1,
                                carrier=PsiCarrier(kind="RESULT", tag=command, payload=summary_payload)
                            )
                            await self.node.bus.publish(result_event)
                            
            except Exception as e:
                self.log.error(f"[exec] Flow Failed: {e}")
                import traceback; traceback.print_exc()
                if self.node and response_channel:
                    error_payload = {"type": "ERROR", "status": "FAILED", "summary": str(e)}
                    await self.node.redis.publish(response_channel, json.dumps(error_payload))
            finally:
                self.completion_signal.set()
                
        return []


def execute_flow_cli_task(flow_instance, command_name: str = "flow_run", payload: dict = None):
    payload = payload or {}
    try:
        asyncio.run(_async_run_flow_in_node(flow_instance, command_name, payload))
    except KeyboardInterrupt:
        log.info("[CLI] Flow interrupted by user.")

async def _async_run_flow_in_node(flow_instance, command_name: str, payload: dict):
    r = redis_async.from_url(REDIS_URL, decode_responses=True)
    
    ## (스웜 감지 및 Node Spawn 로직은 기존 cli 모듈과 동일하게 적용 - 생략 가능하나 원본 유지)
    active_node_keys = await r.keys("runtime:heartbeat:*")
    queue_len = await r.llen("runtime:queue")
    if not active_node_keys or queue_len > 5:
        log.info("[CLI] Spawning background Ambient Node for Flow execution...")
        subprocess.Popen(
            [sys.executable, "-m", "plane.node.runtime"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True, env=os.environ.copy()
        )
        for _ in range(10):
            await asyncio.sleep(0.5)
            if await r.keys("runtime:active"): break

    task_id = f"flow-{uuid.uuid4().hex[:8]}"
    with flow_scope(flow_id=task_id, phase="CLI_FLOW"):
        response_channel = f"res:{task_id}"
        log_channel = f"log:{task_id}"

        pubsub = r.pubsub()
        await pubsub.subscribe(response_channel, log_channel)
        print(f"\n[\033[94mREMOTE STREAM\033[0m] Subscribed to Node ({task_id})")

        # 노드에게 Flow 실행 명령 전달
        trigger_event = PsiEvent(
            event_id=task_id,
            source_id=f"{command_name}:proxy",
            scope="GLOBAL",
            parent_id=None,
            tick=1,
            carrier=PsiCarrier(kind="COMMAND", tag=command_name.lower(), payload=payload),
            context={"response_channel": response_channel}
        )
        await r.lpush("runtime:queue", json.dumps(asdict(trigger_event)))

        try:
            # 60초 타임아웃 방어 (필요시 스트림이 길면 늘림)
            async with asyncio.timeout(120):
                async for msg in pubsub.listen():
                    if msg["type"] != "message": continue

                    channel = msg["channel"]
                    
                    # 로그 채널 처리
                    if channel == log_channel:
                        try:
                            log_data = json.loads(msg["data"])
                            if log_data.get("context", {}).get("phase") == "CLI_FLOW": continue
                            from dataclasses import fields
                            valid_fields = {f.name for f in fields(LogEvent)}
                            clean_data = {k: v for k, v in log_data.items() if k in valid_fields}
                            surface.update(LogEvent(**clean_data))
                        except Exception:
                            continue 
                            
                    # 실시간 Flow 응답 채널 처리 (핵심 변경점)
                    elif channel == response_channel:
                        try:
                            data = json.loads(msg["data"])
                            msg_type = data.get("type", "UNKNOWN")

                            if msg_type == "FLOW":
                                print(f" ├─ [FLOW:{data.get('phase')}] {data.get('psi')} -> {data.get('phi')} (Bound: {data.get('bound')})")
                                # [중요] 흐름의 중간 단계이므로 loop를 탈출하지 않음
                                continue 
                                
                            elif msg_type == "COLLAPSE":
                                print(f" └─ [\033[92mCOLLAPSE\033[0m] {data.get('summary')}")
                                print(f"\n(Flow historical artifacts saved at Redis -> {data.get('detail_key')})")
                                return # [중요] 종결 이벤트 수신 시 대기 종료
                                
                            elif msg_type == "ERROR":
                                print(f" └─ [\033[91mERROR\033[0m] {data.get('summary')}")
                                return
                                
                        except Exception as e:
                            log.error(f"[CLI] Failed to parse flow stream data: {e}")
                            break
        except TimeoutError:
            log.error(f"[CLI] Flow stream timed out. Node stopped reflecting.")
        finally:
            await pubsub.unsubscribe(response_channel)
            await r.close()

class FlowTaskAdapter:
    """
    순수 비동기 제너레이터(AsyncGenerator)를 RMFlow 패턴(FlowEvent, CollapseEvent)으로 
    강제 포장해주는 어댑터 (기존 코드가 이 패턴을 따르지 않을 때 사용)
    """
    def __init__(self, target_generator: AsyncGenerator, phase_name: str = "ADAPTED_FLOW"):
        self.target_generator = target_generator
        self.phase_name = phase_name

    async def execute(self):
        """가짜 FlowEvent와 CollapseEvent를 생성하여 yield"""
        from collections import namedtuple
        PseudoEvent = namedtuple("Event", ["phase", "psi", "phi", "boundary", "surface"])
        PseudoField = namedtuple("Field", ["name"])
        
        count = 0
        try:
            async for raw_item in self.target_generator:
                count += 1
                # 외부 모델이 그냥 dict를 반환한다고 가정
                yield PseudoEvent(
                    phase=self.phase_name,
                    psi=PseudoField(f"step-{count}"),
                    phi=PseudoField("processing"),
                    boundary=PseudoField(str(raw_item)),
                    surface=None
                )
            
            yield PseudoEvent(
                phase=self.phase_name,
                psi=PseudoField("end"), phi=PseudoField("done"), boundary=PseudoField("done"),
                surface=PseudoField("successful-collapse")
            )
        except Exception as e:
            raise e