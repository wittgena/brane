# xphi.flow.ktory
## @lineage: anchor.xphi.flow.ktory
## @lineage: watcher.kernel.xphi.flow.ktory
import sys
import os
import re
import json
import time
import redis
import argparse
import traceback
import subprocess
import urllib.request
import urllib.parse
from typing import List, Optional, Generator
from pathlib import Path
from dataclasses import dataclass, field

from arch.xor.block.schema import Contract
from phase.bind.resolver import find_current_self, resolve_path
from phase.bind.client.stream import StreamClient
from phase.bind.client.surface import RedisClient, SurfaceClient

from xphi.runtime import XPhiRuntime
from watcher.plane.emitter import get_emitter

log = get_emitter("xphi.ktory")

try:
    SELF_ROOT = find_current_self()
    LIB_ROOT = resolve_path("lib")
except Exception as e:
    log.error(f"[error] 기준면(anchor)을 찾을 수 없음: {e}")
    sys.exit(1)

KTORY_API_BASE = os.getenv("KTORY_API_BASE", "http://localhost:8079")
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

class Ktory(SurfaceClient):
    def __init__(self):
        super().__init__(
            stream_client=StreamClient(),
            bootstrap_runtime=XPhiRuntime(LIB_ROOT),
            redis_surface=RedisClient(REDIS_HOST, REDIS_PORT),
            source_name="surface.ktory",
            fallback_url=KTORY_API_BASE,
            path_prefix="/ktory/analyze"
        )

    def _execute_request(self, req: urllib.request.Request, is_json: bool = True) -> Generator:
        """
        [Override] stream.py를 수정하지 않고 TypeError를 우회하기 위한 커스텀 실행기.
        StreamClient.stream()이 is_json 인자를 받지 못하는 문제를 이 레벨에서 차단합니다.
        """
        retried = False
        while True:
            try:
                # 핵심 수정: is_json 인자를 제거하고 호출
                yield from self.stream.stream(req)
                return
            except Exception as e:
                endpoint = req.full_url
                log.error(f"[stream error] {e} at {endpoint}")
                
                if not retried:
                    log.warning(f"[{self.source_name}] Boundary unresponsive. Bootstrapping new runtime...")
                    self._current_endpoint = None # 기존 위상 폐기
                    self.bootstrap_runtime.ensure()
                    
                    time.sleep(2.0) # 런타임 안정화 대기
                    retried = True
                    new_endpoint = self._resolve_endpoint()
                    req = urllib.request.Request(
                        new_endpoint,
                        data=req.data,
                        method=req.method,
                        headers=req.headers
                    )
                    continue
                
                raise RuntimeError(f"{self.source_name} system boundary is completely collapsed.")

    def analyze(self, base_dir: str) -> Generator:
        """Ktory 특화 비즈니스 로직"""
        data = f"path={base_dir}".encode()
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        # is_json=True 명시를 제거 (오버라이딩된 메서드가 알아서 처리함)
        yield from self.request(data=data, method="POST", headers=headers)

class EmitTool:
    name: str

    def emit(self, base_dir: str) -> List[Contract]:
        raise NotImplementedError

class KotlinPSITool(EmitTool):
    name = "ktory"

    def __init__(self):
        self.client = Ktory()

    def emit(self, base_dir: str) -> List[Contract]:
        contracts: List[Contract] = []
        try:
            for obj in self.client.analyze(base_dir):
                self._append_contracts(obj, contracts)
        except Exception as e:
            log.error("[ktory] Final execution failed after retries.")
            raise e
        return contracts

    def _append_contracts(self, obj, contracts: List[Contract]):
        file_outputs = obj if isinstance(obj, list) else [obj]

        for file_out in file_outputs:
            source = file_out.get("source")
            for f in file_out.get("facts", []):
                contracts.append(
                    Contract(
                        kind=f.get("kind"),
                        name=f.get("name"),
                        features=f.get("features", []),
                        refs=f.get("refs", []),
                        location=f.get("location"),
                        source=source
                    )
                )

class RipgrepTool(EmitTool):
    name = "ripgrep"

    def emit(self, base_dir: str) -> List[Contract]:
        facts: List[Contract] = []
        cmd = ["rg", "--line-number", "suspend fun", base_dir]
        try:
            output = subprocess.check_output(cmd, text=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            return facts

        for line in output.splitlines():
            m = re.match(r"(.+):(\d+):", line)
            if not m:
                continue

            file, lineno = m.groups()
            facts.append(
                Contract(
                    kind="function",
                    name=None,
                    features=["suspend"],
                    refs=[],
                    location=f"{file}:{lineno}",
                    source=self.name
                )
            )
        return facts

class EmissionRunner:
    def __init__(self, tools: List[EmitTool]):
        self.tools = tools

    def run(self, base_dir: str) -> List[Contract]:
        all_facts: List[Contract] = []
        for tool in self.tools:
            try:
                emitted = tool.emit(base_dir)
                print(f"[{tool.name}] emitted {len(emitted)} fact(s)")
                all_facts.extend(emitted)
            except Exception:
                print(f"[{tool.name}] failed")
                traceback.print_exc()
        return all_facts

def dump_facts(facts: List[Contract]):
    print("\n## @emit.contracts")
    for i, f in enumerate(facts, 1):
        print(f"\n#{i}")
        print(f"  kind     : {f.kind}")
        print(f"  name     : {f.name}")
        print(f"  features : {f.features}")
        print(f"  refs     : {f.refs}")
        print(f"  location : {f.location}")
        print(f"  source   : {f.source}")

def main():
    parser = argparse.ArgumentParser(
        description="Execution Emission runner for reconst.ktast.fact.model"
    )
    parser.add_argument("--repo", required=True, help="Base directory to scan")
    args = parser.parse_args()

    tools = [
        KotlinPSITool(),
        RipgrepTool(),
    ]

    runner = EmissionRunner(tools)
    facts = runner.run(args.repo)
    dump_facts(facts)

if __name__ == "__main__":
    main()