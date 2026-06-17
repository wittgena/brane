# arch.contract.registry.path
## @lineage: topos.contract.registry.path
## @lineage: phase.runtime.contract.registry.path
import os
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
from phase.bind.resolver import find_current_self, load_bound, resolve_path as legacy_resolve
from watcher.plane.emitter import get_emitter

log = get_emitter('contract.path')

class PathRegistry:
    """
    Topos 시스템의 경로 SSOT(Single Source of Truth) 관리자.
    """
    def __init__(self):
        self._aliases: Dict[str, str] = {}
        self._access_history: List[Dict[str, Any]] = []
        self._initialized = False

    def lazy_sync(self):
        """시스템 부팅 후 resolver를 통해 bound.json과 동기화"""
        if self._initialized: return
        try:
            from phase.bind.resolver import find_current_self, load_bound
            self_root = find_current_self()
            bound = load_bound(self_root)
            self._aliases = bound.get("paths", {})
            self._initialized = True
            log.info(f"[PathRegistry] Synced {len(self._aliases)} aliases.")
        except Exception as e:
            log.debug(f"[PathRegistry] Sync deferred: {e}")

    def log_access(self, alias: str, actual_path: Path):
        """
        [FIX] 외부에서 호출 가능한 공개 메서드.
        기존에 누락되었던 메서드입니다.
        """
        self.lazy_sync()
        is_managed = alias in self._aliases
        
        # Shadow IO 감지 시 경고 출력
        if not is_managed and not str(actual_path).startswith(("/tmp", "/dev")):
            log.warning(f"⚠️ [ShadowIO] Unmanaged path: '{alias}' -> {actual_path}")

        self._access_history.append({
            "alias": alias,
            "path": str(actual_path),
            "managed": is_managed,
            "timestamp": os.path.getmtime(actual_path) if actual_path.exists() else None
        })

    def resolve(self, name: str, start: Path | None = None) -> Path:
        """기존 resolve_path를 호출하고 기록을 남깁니다."""
        from phase.bind.resolver import resolve_path as legacy_resolve
        resolved = legacy_resolve(name, start)
        self.log_access(name, resolved)
        return resolved

path_registry = PathRegistry()

def path_contract(alias: str):
    """
    데코레이터: 특정 함수나 클래스가 사용하는 경로를 명시합니다.
    contract.proposer가 이 정보를 읽어 '노드-파일' 간의 연결 구조(Lineage)를 그립니다.
    """
    def decorator(target):
        if not hasattr(target, "__path_contracts__"):
            target.__path_contracts__ = []
        target.__path_contracts__.append(alias)
        return target
    return decorator