# phase.bind.client.surface
## @lineage: phase.bound.client.surface
## @lineage: phase.reflect.client.surface
import urllib.request
import urllib.parse
from urllib.error import HTTPError, URLError
import json
import time
from dataclasses import dataclass, field
from typing import List, Optional, Generator
from pathlib import Path
import subprocess
import re
import argparse
import traceback
import sys
import os
import redis
from watcher.plane.emitter import get_emitter

log = get_emitter("client.system")

class RedisClient:
    """Surface listener & Echolocator"""
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.pool = redis.ConnectionPool(host=self.host, port=self.port, decode_responses=True)

    def listen_job(self, channel:str):
        """분산 작업 완료 로그를 수신"""
        r = redis.Redis(connection_pool=self.pool)
        pubsub = r.pubsub()
        pubsub.subscribe(channel)
        log.info(f"[redis] Subscribed to job: {channel}")

        for msg in pubsub.listen():
            if msg["type"] != "message":
                continue
            try:
                yield json.loads(msg["data"])
            except Exception:
                continue

    def echolocate(self, source: str = "surface.probe", timeout: float = 2.0) -> Optional[str]:
        """system:ping 교란을 통해 현재 활성화된 노드의 반향(echo)을 수집합니다."""
        r = redis.Redis(connection_pool=self.pool)
        pubsub = r.pubsub()
        
        pubsub.subscribe("system:echo")
        log.info(f"[{source}] Perturbing system to find active boundary...")
        r.publish("system:ping", json.dumps({"ts": time.time(), "source": source}))

        start_time = time.time()
        active_url = None

        while time.time() - start_time < timeout:
            msg = pubsub.get_message(ignore_subscribe_messages=True, timeout=0.5)
            if msg:
                try:
                    data = json.loads(msg["data"])
                    if "api_base" in data:
                        raw_url = data["api_base"]
                        parsed = urllib.parse.urlparse(raw_url)
                        active_url = f"{parsed.scheme}://{parsed.netloc}"
                        
                        log.info(f"[echo] Resonance detected. Base Origin: {active_url}")
                        break
                except Exception:
                    continue

        pubsub.close()
        return active_url

class SurfaceClient:
    """
    Bound <-> Resolver <-> Surface 통신을 조율하는 기본 클라이언트.
    동적 위상 라우팅(Echolocation) 및 런타임 자가 치유(Self-healing)를 담당합니다.
    """
    def __init__(self, stream_client, bootstrap_runtime, redis_surface, source_name: str, fallback_url: str, path_prefix: str = ""):
        self.stream = stream_client
        self.bootstrap_runtime = bootstrap_runtime
        self.surface = redis_surface
        self.source_name = source_name
        self.fallback_url = fallback_url
        self.path_prefix = path_prefix 
        self._current_endpoint = None

    def _ping(self, base_url: str) -> bool:
        """가벼운 PsiEvent를 /psi 엔드포인트로 던져 xphi 서버의 실제 응답(accepted)을 확인"""
        target_url = f"{base_url.rstrip('/')}/psi"
        ping_payload = json.dumps({
            "channel": "system:ping",
            "sourceId": self.source_name,
            "data": "ping_check"
        }).encode('utf-8')

        try:
            req = urllib.request.Request(
                target_url, 
                data=ping_payload, 
                method="POST",
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=1.5) as response:
                result = response.read().decode('utf-8').strip()
                if result == "accepted":
                    log.debug(f"[{self.source_name}] Psi event accepted by {base_url}")
                    return True
                else:
                    # accepted가 아니더라도 200 OK라면 서버는 살아있음
                    return True

        except HTTPError as e:
            # 404, 405 등의 에러가 발생했다는 것은 "해당 포트에 어떤 서버 프로세스가 떠서 응답은 했다"는 뜻.
            # 이 경우 포트 충돌 방지를 위해 일단 살아있는 것으로 간주(True)하고 부트스트랩을 막습니다.
            log.debug(f"[{self.source_name}] Server is up but returned HTTP {e.code} at /psi. Bypassing bootstrap.")
            return True
            
        except URLError as e:
            # Connection Refused, Timeout 등 아예 TCP 접속조차 안 되는 진짜 사망 상태
            log.warning(f"[{self.source_name}] Boundary collapsed (URLError): {e.reason}")
            return False
            
        except Exception as e:
            log.error(f"[{self.source_name}] Unexpected ping anomaly: {e}")
            return False

    def ensure_boundary(self) -> str:
        """
        1. 현재 캐시된 위상 /psi 핑 테스트
        2. 실패 시 Echolocation 시도
        3. 실패 시 Fallback URL /psi 핑 테스트
        4. 전부 실패 시 명시적 Bootstrap 실행
        """
        if self._current_endpoint and self._ping(self._current_endpoint.replace(self.path_prefix, "")):
            return self._current_endpoint

        base_origin = self.surface.echolocate(source=self.source_name, timeout=1.0)

        if not base_origin:
            fallback_origin = f"{urllib.parse.urlparse(self.fallback_url).scheme}://{urllib.parse.urlparse(self.fallback_url).netloc}"
            if self._ping(fallback_origin):
                base_origin = fallback_origin
            else:
                log.warning(f"[{self.source_name}] Surface collapsed. Forcing runtime bootstrap...")
                self.bootstrap_runtime.ensure()
                base_origin = fallback_origin

        self._current_endpoint = f"{base_origin}{self.path_prefix}"
        return self._current_endpoint

    def request(self, query_path: str = "", data: bytes = None, method: str = "GET", headers: dict = None, is_json: bool = True) -> Generator:
        full_url = f"{self.ensure_boundary()}{query_path}"
        req_headers = headers or {}
        req = urllib.request.Request(full_url, data=data, method=method, headers=req_headers)
        
        try:
            yield from self.stream.stream(req, is_json=is_json)
        except HTTPError as e:
            # 서버가 살아있고 명확한 HTTP 에러를 뱉은 경우 (404, 405 등)
            # 이는 위상 붕괴가 아니라 단순한 '경로 오류'나 '서버 내부 오류'이므로 복구를 시도하지 않음
            log.error(f"[{self.source_name}] Request failed with HTTP {e.code}: {full_url}")
            # 필요한 경우 raise e 대신 빈 결과를 넘길 수도 있습니다.
            raise 
        except URLError as e:
            # 네트워크 단절, Connection Refused 등 진짜 위상이 붕괴된 경우에만 복구 시도
            log.error(f"[{self.source_name}] Boundary collapsed (URLError: {e.reason}). Realigning...")
            self._current_endpoint = None 
            full_url = f"{self.ensure_boundary()}{query_path}"
            req = urllib.request.Request(full_url, data=data, method=method, headers=req_headers)
            yield from self.stream.stream(req, is_json=is_json)
        except Exception as e:
            log.error(f"[{self.source_name}] Unexpected stream anomaly: {e}")
            raise