# xphi.runtime
## @lineage: anchor.xphi.runtime
## @lineage: watcher.kernel.xphi.runtime
## @lineage: watcher.gateway.xphi.runtime
## @lineage: gateway.xphi.runtime
## @lineage: xe.xphi.runtime
import os
import sys
import json
import time
import subprocess
import threading
import urllib.request
import urllib.parse
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional, Generator
import redis

from phase.bind.resolver import find_current_self, resolve_path
from watcher.plane.emitter import get_emitter

log = get_emitter("xphi.runtime")

try:
    LIB_ROOT = resolve_path("lib")
except Exception as e:
    log.error(f"[error] 기준면(anchor)을 찾을 수 없음: {e}")
    sys.exit(1)

class XPhiRuntime:
    """activate resolver when boundary has no handler"""
    def __init__(self, jar_root: Path = LIB_ROOT):
        self.jar_root = jar_root
        
        # [3안 보조] Redis 클라이언트 초기화 
        redis_host = os.getenv("REDIS_HOST", "localhost")
        self.redis = redis.Redis(host=redis_host, decode_responses=True)
        
        # [2안 메인] 식별을 위한 프로세스 고유 이름
        self.process_name = "surgent-xphi-node" 

    def ensure(self):
        jars = sorted(self.jar_root.glob("xphi-*.jar"))
        if not jars:
            raise RuntimeError("xphi jar not found")

        jar = jars[-1]
        log.info(f"[bootstrap] start xphi: {jar}")

        ## exec -a를 통한 OS 레벨 프로세스명 변경 및 JVM 프로퍼티 태깅
        cmd = [
            "bash", "-c",
            f"exec -a {self.process_name} java -Dreaper.tag={self.process_name} -jar {jar}"
        ]

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        pid = proc.pid
        
        ## 띄운 직후 PID를 규격화된 Redis Set에 등록
        try:
            self.redis.sadd("system:xphi:pids", pid)
            log.info(f"[bootstrap] Registered PID {pid} to Redis Registry (system:xphi:pids)")
        except Exception as e:
            log.warning(f"[bootstrap] Failed to register PID to Redis (Continuing anyway): {e}")

        log.info("[bootstrap] Waiting for resonance (3s)...")
        time.sleep(3)