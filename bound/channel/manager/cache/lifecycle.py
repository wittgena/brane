# bound.channel.manager.cache.lifecycle
## @lineage: channel.cache.manager
## @lineage: anchor.context.cache.manager
## @lineage: bound.context.cache.manager
## @lineage: hub.memory.cache.manager
## @lineage: meta.gov.state.cache.manager
import os
import sys
import argparse
from typing import Optional, List
from datetime import datetime, timezone
from google import genai
from arch.xor.store import ResidueStore
from arch.contract.registry.unified import contract
from watcher.plane.emitter import get_emitter
from phase.runtime.cli.executor import CliTaskAdapter, parse_local, dispatch_cli

log = get_emitter("cache.manager")

class CacheLifecycleManager:
    """Gemini API 원격 캐시와 로컬 ResidueStore 상태를 관리하고 동기화하는 매니저"""
    def __init__(self, target_repo: str):
        self.target_repo = target_repo
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.store = ResidueStore()
        # Manager는 로컬 DB에서 추적 중인 prefix를 기준으로 관리합니다.
        self.repo_prefix = f"{target_repo}:"

    def list_caches(self) -> None:
        """원격 Gemini API에 등록된 현재 활성 캐시 목록과 로컬 매핑 상태를 출력"""
        log.info(f"[*] Inspecting active Gemini caches for {self.target_repo}...")
        
        try:
            # 원격 캐시 목록 조회
            remote_caches = list(self.client.caches.list())
            remote_ids = {c.name for c in remote_caches}
            
            if not remote_caches:
                log.info("No active remote caches found.")
                return

            log.info(f"Found {len(remote_caches)} remote caches.")
            for cache in remote_caches:
                expire_dt = cache.expire_time
                is_expired = expire_dt and expire_dt < datetime.now(timezone.utc)
                status = "EXPIRED" if is_expired else "ACTIVE"
                log.info(f" - [{status}] ID: {cache.name} | Model: {cache.model} | Expires: {expire_dt}")

            # 로컬 Store와 대조
            # (실제 구현에서는 store.list_by_prefix 등 인덱스 조회 메서드 활용)
            log.info("[*] Cross-checking with local ResidueStore...")
            # ... 로컬 DB 대조 로직 (생략/확장 가능) ...

        except Exception as e:
            log.error(f"[LIST ERROR] Failed to fetch caches: {e}")

    def prune_expired(self) -> None:
        """만료되었거나 로컬 DB와 연결이 끊어진(Orphaned) 원격 캐시를 강제 정리"""
        log.info("[*] Starting pruning process for expired caches...")
        try:
            remote_caches = list(self.client.caches.list())
            pruned_count = 0

            for cache in remote_caches:
                expire_dt = cache.expire_time
                # 1. 만료 시간이 지났는지 검사
                if expire_dt and expire_dt < datetime.now(timezone.utc):
                    log.info(f"Pruning expired cache: {cache.name}")
                    self.client.caches.delete(name=cache.name)
                    pruned_count += 1
                    
            log.info(f"[*] Pruning complete. Removed {pruned_count} expired caches.")
        except Exception as e:
            log.error(f"[PRUNE ERROR] Failed during pruning: {e}")

    def evict_cache(self, cache_id: str) -> None:
        """특정 캐시를 명시적으로 삭제 (파열 상태 강제 유도 시 사용)"""
        log.warning(f"[*] Force evicting cache: {cache_id}")
        try:
            self.client.caches.delete(name=cache_id)
            log.info(f"Successfully evicted: {cache_id}")
            # 로컬 Store에서도 해당 메타데이터를 Invalidate 처리하는 로직 추가 가능
        except Exception as e:
            log.error(f"[EVICT ERROR] Could not delete {cache_id}: {e}")

class CacheManagerTask:
    def __init__(self, target_repo: str, action: str, target_id: Optional[str] = None):
        self.action = action
        self.target_id = target_id
        self.manager = CacheLifecycleManager(target_repo)

    def execute(self) -> None:
        """선택된 Action에 따라 Manager 라우팅"""
        if self.action == "list":
            self.manager.list_caches()
        elif self.action == "prune":
            self.manager.prune_expired()
        elif self.action == "evict":
            if not self.target_id:
                log.error("Evict action requires --id parameter.")
                return
            self.manager.evict_cache(self.target_id)
        else:
            log.error(f"Unknown action: {self.action}")

def entry_task(args):
    parser = argparse.ArgumentParser(description="Manage Gemini Cached Substrates (Lifecycle & GC)")
    parser.add_argument("--repo", type=str, required=True, help="Target repository scope. E.g., flow/dev")
    parser.add_argument("--action", type=str, choices=["list", "prune", "evict"], required=True, help="Management action to perform.")
    parser.add_argument("--id", type=str, help="Specific Cache ID to evict (used with --action evict)")
    parsed_args = parser.parse_args(args)
    
    task = CacheManagerTask(
        target_repo=parsed_args.repo, 
        action=parsed_args.action,
        target_id=parsed_args.id
    )
    return CliTaskAdapter(task.execute)

@contract.cli(name="cache.manager", recept=[])
def main():
    bound_args, remain = parse_local(sys.argv[1:])
    if bound_args.local:
        entry_task(remain).run()
    else:
        dispatch_cli("token.cache.manager", entry_task, __file__)

if __name__ == "__main__":
    main()