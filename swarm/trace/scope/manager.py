# swarm.trace.scope.manager
## @lineage: bound.scope.manager
## @lineage: gov.scope.manager
from abc import ABC, abstractmethod
import os
import subprocess
import sys
import time
import threading
import httpx
import socket
import redis
from dataclasses import dataclass
from typing import Optional
from phase.bind.client.engine.local import LLMEngine
from phase.bind.resolver import resolve_path
from watcher.plane.emitter import get_emitter
from contextlib import ExitStack
from gov.scope.dsp import settings
from agent.llm.factory.state import GraphEngine
from meta.xor.adapter.lm.local import LocalLM
from gov.scope.thch import thch_scope
from gov.scope.surface.config import BaseSurface, SurfaceConfig, get_free_port
from gov.scope.surface.dphi import DphiSurface

RES_ROOT = resolve_path("res")
log = get_emitter("scope.manager")

class LocalSurface(BaseSurface):
    def __init__(self):
        self.engine = LLMEngine()

    def up(self):
        log.info("[*] Initializing Local Direct Surface...")
        self.engine.ensure_server()
        start_time = time.time()
        ready = False
        try:
            time.sleep(2) 
            ready = True
        except Exception:
            log.debug(f"[-] Wait interrupted during Local Surface init: {e}")

        if not ready:
            log.warning("[-] Local Engine might not be fully ready, proceeding anyway.")

    def down(self):
        log.info("[*] Folding Local Surface...")

    def get_engine(self):
        return lambda agent_usage: self.engine

class WASSurface(BaseSurface):
    def __init__(self, config: SurfaceConfig):
        self.config = config
        self.process = None
        self._stop_event = threading.Event()
        self.threads = []
        self.llm_engine = LLMEngine()
        
        # [2안 메인] & [3안 보조] 상태 관리를 위한 Redis 및 태깅 설정
        redis_host = os.getenv("REDIS_HOST", "localhost")
        self.redis = redis.Redis(host=redis_host, decode_responses=True)
        self.process_name = "surgent-was"
        self.registry_key = "system:was:pids"

    def stream_output(self, pipe, prefix: str):
        try:
            for line in iter(pipe.readline, ""):
                if self._stop_event.is_set():
                    break
                if line:
                    sys.stdout.write(f"[{prefix}] {line}")
                    sys.stdout.flush()
        finally:
            pipe.close()

    def up(self):
        # 포트 충돌 방지: 설정된 포트부터 빈 포트 스캔
        self.config.port = get_free_port(self.config.port)
        self.base_url = f"http://{self.config.host}:{self.config.port}"

        log.info(f"[*] Booting WAS Surface on {self.base_url}...")
        self.llm_engine.ensure_server()
        # import meta.ops.was.launcher as was_launcher_module

        ## bash의 exec -a를 활용해 파이썬 프로세스 이름을 강제 변경
        cmd_str = f"exec -a {self.process_name} {sys.executable} -m {was_launcher_module.__name__} --host {self.config.host} --port {self.config.port}"
        cmd = ["bash", "-c", cmd_str]
        
        env = {**os.environ, "LOG_JSON": "true", "PYTHONUNBUFFERED": "1"}
        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE if self.config.show_logs else subprocess.DEVNULL,
            stderr=subprocess.PIPE if self.config.show_logs else subprocess.DEVNULL,
            text=True, env=env, bufsize=1
        )

        pid = self.process.pid
        
        ## 시작과 동시에 Redis 레지스트리에 PID 등록
        try:
            self.redis.sadd(self.registry_key, pid)
            log.info(f"[*] Registered WAS PID {pid} to {self.registry_key}")
        except Exception as e:
            log.warning(f"[-] Failed to register WAS PID to Redis: {e}")

        if self.config.show_logs and self.process.stdout and self.process.stderr:
            t1 = threading.Thread(target=self.stream_output, args=(self.process.stdout, "SURFACE:OUT"), daemon=True)
            t2 = threading.Thread(target=self.stream_output, args=(self.process.stderr, "SURFACE:LOG"), daemon=True)
            t1.start()
            t2.start()
            self.threads = [t1, t2]

        start_time = time.time()
        ready = False
        while time.time() - start_time < self.config.timeout:
            if self.process.poll() is not None:
                raise RuntimeError(f"Server exited with code {self.process.returncode}")
            try:
                if httpx.get(f"{self.base_url}/ready", timeout=1.0).status_code < 500:
                    ready = True
                    break
            except (httpx.RequestError, httpx.ConnectError):
                pass
            time.sleep(1)

        if not ready:
            self.down()
            raise RuntimeError("Hand failed to stabilize within timeout.")

        log.info(f"\n[+] Hand stabilized at {self.base_url}\n")

    def down(self):
        if self.process:
            log.info("[*] Folding WAS Surface (Teardown)...")
            self._stop_event.set()
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            
            ## 정상 종료 시 레지스트리에서 해당 PID만 제거
            try:
                self.redis.srem(self.registry_key, self.process.pid)
                log.info(f"[+] Unregistered WAS PID {self.process.pid} from {self.registry_key}")
            except Exception as e:
                pass
            log.info("[+] WAS Surface process terminated.")

    def get_engine(self):
        return lambda agent_usage: GraphEngine(self.base_url, agent_usage)

class SurfaceManager:
    def __init__(self, config: SurfaceConfig):
        self.config = config
        if config.use_was:
            self.impl = WASSurface(config)
        elif config.use_dphi:
            self.impl = DphiSurface(config)
        else:
            self.impl = LocalSurface()

    def __enter__(self):
        self.impl.up()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.impl.down()
        log.info("[+] Context Manager: Surface closed.")

    def get_engine(self):
        return self.impl.get_engine()

def managed_scope(**kwargs):
    config = SurfaceConfig(**kwargs)
    return SurfaceManager(config)

if __name__ == "__main__":
    with managed_scope(use_dphi=True) as manager:
        lm = manager.get_engine()(agent_usage=None)
        model_name = "unknown"
        if hasattr(lm, "kwargs"):
            model_name = lm.kwargs.get("model", "unknown")
            
        log.info(f"Surface is active. Active LM: {model_name}")