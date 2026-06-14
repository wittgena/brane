# anchor.xphi.flow.xearch
## @lineage: watcher.kernel.xphi.flow.xearch
"""@desc: Bound → Resolver → Surface orchestration for xphi (Echolocation Routing)"""
import os
import sys
import json
import time
import redis
import subprocess
import threading
import urllib.request
import urllib.parse
from typing import List, Optional, Generator
from pathlib import Path
from dataclasses import dataclass
from phase.bind.resolver import find_current_self, resolve_path
from watcher.plane.emitter import get_emitter
from anchor.xphi.runtime import XPhiRuntime
from phase.bind.client.stream import StreamClient
from phase.bind.client.surface import RedisClient, SurfaceClient

log = get_emitter("xphi.xearch")

try:
    SELF_ROOT = find_current_self()
    LIB_ROOT = resolve_path("lib")
    BLOCKS_ROOT = resolve_path("blocks")
except Exception as e:
    log.error(f"[error] 기준면(anchor)을 찾을 수 없음: {e}")
    sys.exit(1)

# XPHI_API_BASE는 이제 Fallback(최후의 수단)으로만 씁니다.
XPHI_API_BASE = os.getenv("XPHI_API_BASE", "http://localhost:8079")
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

@dataclass
class SearchResult:
    """projection of Φ⁺ result into CLI-readable form"""
    score: float
    block_type: str
    section_path: str
    file_path: str

class Xor(SurfaceClient):
    def __init__(self):
        super().__init__(
            stream_client=StreamClient(),
            bootstrap_runtime=XPhiRuntime(LIB_ROOT),
            redis_surface=RedisClient(REDIS_HOST, REDIS_PORT),
            source_name="surface.xor",
            fallback_url=XPHI_API_BASE,
            path_prefix="/xor"
        )

    def index_dist(self, target_path: str):
        query = "/index-dist?" + urllib.parse.urlencode({"path": target_path})
        
        # 부모의 request 호출 (내부적으로 ensure_boundary -> 실행 -> 복구가 자동으로 처리됨)
        for msg in self.request(query_path=query, method="POST", is_json=False):
            if msg.startswith("jobId:"):
                job_id = msg.split("jobId:")[1].strip()
                log.info(f"[job] {job_id}")
                threading.Thread(target=self._redis_loop, args=(job_id,), daemon=True).start()
            else:
                print(f"[REST] {msg}")

    def _redis_loop(self, job_id: str):
        channel = f"xor:result:{job_id}"
        for data in self.surface.listen_job(channel):
            blocks = len(data.get("blocks", []))
            print(f"\n[Redis] files={len(data.get('filePaths', []))} blocks={blocks}")

    def search(self, query: str, block_type: Optional[str] = None) -> List[SearchResult]:
        params = {"query": query}
        if block_type:
            params["type"] = block_type
        
        query_path = "/search?" + urllib.parse.urlencode(params)
        headers = {"Accept": "text/event-stream"}
        
        results = []
        # 부모의 request 호출 (내부적으로 ensure_boundary -> 실행 -> 복구가 자동으로 처리됨)
        for item in self.request(query_path=query_path, method="GET", headers=headers, is_json=True):
            try:
                results.append(SearchResult(
                    score=float(item.get("score", 0.0)),
                    block_type=item.get("blockType", "unknown"),
                    section_path=item.get("sectionPath", "unknown"),
                    file_path=item.get("filePath", "unknown")
                ))
            except Exception:
                continue
        return results

def main():
    args = sys.argv[1:]
    if not args:
        print("usage: index | search")
        sys.exit(1)

    client = Xor()

    if args[0] == "index":
        client.index_dist()
    elif args[0] == "search":
        query = " ".join(args[1:]) # 단순화
        results = client.search(query)
        print(f"\n[results] {len(results)}\n")
        for r in results:
            print(f"{r.score:.3f} | {r.block_type} | {r.section_path} | {r.file_path}")
    else:
        print("unknown command")

if __name__ == "__main__":
    main()