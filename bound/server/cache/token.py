# bound.server.cache.token
## @lineage: bound.proxy.cache.token
## @lineage: anchor.router.cache.token
## @lineage: bound.router.cache.token
## @lineage: bound.router.manager.cache.token
## @lineage: bound.channel.manager.cache.token
## @lineage: channel.cache.token
## @lineage: anchor.context.cache.token
## @lineage: bound.context.cache.token
## @lineage: hub.memory.cache.token
## @lineage: meta.gov.state.cache.token
import os
import sys
import argparse
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple, Set
from collections import defaultdict
from google import genai
from google.genai import types
from arch.xor.store import ResidueStore, ResidueSnapshot
from arch.contract.registry.unified import contract
from watcher.plane.emitter import get_emitter
from phase.runtime.cli.executor import CliTaskAdapter, parse_local, dispatch_cli

log = get_emitter("token.cache")
DELIMITER = "---"

class PlaneType:
    GEMINI = "GEMINI"   # 전역 위상 (Core Topology)
    AGENT = "AGENT"     # 실행 평면 (Execution & Agency)
    ORACLE = "ORACLE"   # 불변 평면 (Registry & Primitives)

class MultiPlaneCacheProjector:
    """다중 위상 평면(Multi-Plane) 캐시 프로젝터"""
    def __init__(self, target_repo: str, model_name: str = "gemini-3-flash", ttl_hours: int = 2):
        self.target_repo = target_repo
        self.model_name = model_name
        self.ttl_seconds = str(ttl_hours * 3600) + "s"
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    def classify_plane(self, path: Path, content: str) -> str:
        """파일의 위상적 성질을 판별하여 적합한 평면으로 라우팅"""
        if "@primitive" in content or "registry" in path.parts:
            return PlaneType.ORACLE
        elif "@agent" in content or "@operator" in content or "executor" in path.parts:
            return PlaneType.AGENT
        return PlaneType.GEMINI

    def project(self, subgraph: List[Path]) -> List[Tuple[str, str]]:
        representations = []
        for path in subgraph:
            try:
                content = path.read_text(encoding="utf-8", errors="replace").strip()
                plane = self.classify_plane(path, content)
                rel_path = str(path)
                
                final_block = f"\n{DELIMITER} MODULE_PATH: {rel_path} {DELIMITER}\n{content}\n"
                representations.append((plane, final_block))
            except Exception as e:
                log.error(f"[PROJECT ERROR] {path}: {e}")
        return representations

    def assemble(self, representations: List[Tuple[str, str]]) -> Dict[str, str]:
        """평면(Plane)별로 기질을 독립적으로 조립"""
        groups = defaultdict(list)
        for plane, text in representations:
            groups[plane].append(text)
        
        assembled = {}
        for plane, texts in groups.items():
            assembled[plane] = f"[{plane} PLANE START]\n" + "\n".join(texts) + f"\n[{plane} PLANE END]"
        return assembled

    def emit_plane(self, plane: str, text: str) -> Optional[str]:
        """개별 평면을 Gemini API로 투영하고 Cache ID 반환"""
        log.info(f"[*] Emitting new topology for plane: {plane}")
        try:
            cache = self.client.caches.create(
                model=self.model_name,
                config=types.CreateCachedContentConfig(
                    contents=[types.Content(role="user", parts=[types.Part.from_text(text=text)])],
                    ttl=self.ttl_seconds
                )
            )
            return cache.name
        except Exception as e:
            log.error(f"Emit failed for {plane}: {e}")
            return None


class TopologicalExecutor:
    """위상적 텐션을 평가하고 상태를 결정(판별)하는 실행기"""
    def __init__(self, store: ResidueStore, projector: MultiPlaneCacheProjector):
        self.store = store
        self.projector = projector
        # 평면별 텐션 임계치 (ORACLE은 거의 변하지 않고, AGENT는 민감하게 반응함)
        self.thresholds = {
            PlaneType.GEMINI: 0.20,
            PlaneType.AGENT: 0.10,
            PlaneType.ORACLE: 0.05
        }

    def generate_signature(self, symbols: Set[str]) -> str:
        """위상 서명(Topological Signature) 생성: 심볼들의 정렬된 해시"""
        sorted_syms = "".join(sorted(list(symbols)))
        return hashlib.md5(sorted_syms.encode()).hexdigest()[:12]

    def evaluate_tension(self, current_symbols: Set[str], previous_symbols: Set[str]) -> float:
        """현재 상태와 과거 위상 간의 차집합(Delta)을 기반으로 구조적 장력(Tension) 계산"""
        if not previous_symbols:
            return 1.0 # 과거 데이터가 없으면 무조건 100% 파열 (Max Tension)
            
        union = current_symbols.union(previous_symbols)
        intersection = current_symbols.intersection(previous_symbols)
        if not union: return 0.0
        
        # Jaccard Distance를 변형한 텐션 지수
        delta = len(union) - len(intersection)
        return delta / len(union)

    def process_plane(self, target_repo: str, plane_type: str, current_symbols: Set[str], plane_text: str) -> str:
        """단일 평면에 대한 위상 판별 및 처리 로직"""
        current_sig = self.generate_signature(current_symbols)
        threshold = self.thresholds.get(plane_type, 0.2)
        
        # 탐색을 위한 공통 Prefix 생성
        prefix = f"{target_repo}:{plane_type}"

        # 1. 과거 위상 불러오기 (xphi.xor.store 모듈 활용)
        previous_snap = self.store.retrieve_latest(prefix)
        prev_symbols = set(previous_snap.symbols) if previous_snap else set()

        # 2. 텐션 계산 (Tension Evaluation)
        tension = self.evaluate_tension(current_symbols, prev_symbols)
        log.info(f"[{plane_type}] Topological Tension: {tension:.3f} (Threshold: {threshold})")

        # 3. 위상적 판별 (Judgment)
        if tension < threshold and previous_snap and "cache_id" in previous_snap.metadata:
            # 텐션이 낮음 -> 위상 유지
            log.info(f"[{plane_type}] Tension is stable. Retrieving past topological boundary.")
            return previous_snap.metadata["cache_id"]
        else:
            # 텐션 초과 -> 기존 위상 파열 및 평탄화 (Rupture & Flatten)
            log.warning(f"[{plane_type}] Rupture detected! Flattening and projecting new topology...")
            new_cache_id = self.projector.emit_plane(plane_type, plane_text)
            
            if new_cache_id:
                # 통합된 Data Model에 맞추어 스냅샷 생성
                new_snap = ResidueSnapshot(
                    symbols=list(current_symbols),
                    tension=tension,
                    metadata={
                        "plane_type": plane_type,
                        "topology_signature": current_sig,
                        "cache_id": new_cache_id
                    }
                )
                self.store.deposit(new_snap, key_prefix=prefix)
                log.info(f"[DEPOSIT] Formed new topological crystal for {prefix}")
                
            return new_cache_id

class CacheCompileTask:
    def __init__(self, target_repo: str, ttl_hours: int):
        self.target_repo = target_repo
        self.projector = MultiPlaneCacheProjector(target_repo, ttl_hours=ttl_hours)
        self.store = ResidueStore()  # xphi.xor.store의 공통 DB
        self.executor = TopologicalExecutor(self.store, self.projector)

    def compile(self) -> None:
        """캐시 갱신 및 토폴로지 동기화 메인 프로세스"""
        log.info(f"Starting topological compilation for {self.target_repo}")
        # (여기에 실제 파일 탐색, 기호 추출 및 process_plane 루프 로직이 들어갑니다)
        # ex:
        # subgraph = [...] 
        # representations = self.projector.project(subgraph)
        # assembled = self.projector.assemble(representations)
        # for plane_type, text in assembled.items():
        #    symbols = extract_symbols(text)
        #    self.executor.process_plane(self.target_repo, plane_type, symbols, text)
        pass

def entry_task(args):
    parser = argparse.ArgumentParser(description="Freeze project topos into Gemini Cache Subst")
    parser.add_argument("--repo", type=str, required=True, help="Target input path. E.g., flow/dev")
    parser.add_argument("--ttl", type=int, default=2, help="Cache Time-To-Live in hours.")
    parsed_args = parser.parse_args(args)
    
    task = CacheCompileTask(target_repo=parsed_args.repo, ttl_hours=parsed_args.ttl)
    return CliTaskAdapter(task.compile)

@contract.cli(name="token.cache", recept=[])
def main():
    bound_args, remain = parse_local(sys.argv[1:])
    if bound_args.local:
        entry_task(remain).run()
    else:
        dispatch_cli("token.cache", entry_task, __file__)

if __name__ == "__main__":
    main()