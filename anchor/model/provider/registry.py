# anchor.model.provider.registry
## @lineage: anchor.model.router.provider.registry
## @lineage: anchor.model.provider.parser
import json
import os
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Callable
import httpx
from watcher.plane.emitter import get_emitter 
from phase.bind.resolver import resolve_path 

log = get_emitter("provider.registry")

IO_ROOT = Path(resolve_path("io"))
REGISTRY_DIR = IO_ROOT / "llms" / "registry"

def save_local_backup(data: dict, filename: str) -> None:
    """원격에서 성공적으로 가져온 JSON 데이터를 로컬에 백업합니다."""
    try:
        REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
        backup_path = REGISTRY_DIR / filename
        with open(backup_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        log.debug(f"Saved local backup successfully: {backup_path}")
    except Exception as e:
        log.warning(f"Failed to save local backup for {filename}: {e}")

def load_local_backup(filename: str) -> dict:
    """원격 패치 실패 시, 저장된 로컬 백업본을 로드합니다."""
    try:
        backup_path = REGISTRY_DIR / filename
        if backup_path.exists():
            with open(backup_path, "r", encoding="utf-8") as f:
                return json.load(f)
        log.warning(f"Local backup not found at {backup_path}")
    except Exception as e:
        log.error(f"Failed to load local backup for {filename}: {e}")
    return {}

def _optimize_spec_memory(raw_spec: dict) -> dict:
    """희소 데이터(Sparse Data) 제거: False, 0.0, null, 빈 문자열 등을 드랍하여 메모리 점유를 최소화합니다."""
    optimized = {}
    for k, v in raw_spec.items():
        if isinstance(v, dict):
            optimized_sub = _optimize_spec_memory(v)
            if optimized_sub:
                optimized[k] = optimized_sub
        elif v not in (False, 0.0, 0, "", None, [], {}):
            optimized[k] = v
    return optimized

def _expand_model_aliases(model_cost: dict) -> dict:
    """Aliases 리스트를 전개하여 단일 참조로 최상단에 매핑합니다."""
    aliases_to_add: Dict[str, dict] = {}
    keys_with_aliases = []

    for model_name, model_info in model_cost.items():
        if not isinstance(model_info, dict):
            continue
        aliases = model_info.get("aliases")
        if isinstance(aliases, list):
            keys_with_aliases.append(model_name)
            for alias in aliases:
                if alias not in model_cost and alias not in aliases_to_add:
                    aliases_to_add[alias] = model_info 

    for key in keys_with_aliases:
        model_cost[key].pop("aliases", None)

    model_cost.update(aliases_to_add)
    return model_cost

def parse_model_cost_map(raw_data: dict) -> dict:
    """Model Cost Map 전용 통합 파서 훅"""
    expanded = _expand_model_aliases(raw_data)
    # 메모리 다이어트 적용
    for model_name, spec in expanded.items():
        if isinstance(spec, dict):
            expanded[model_name] = _optimize_spec_memory(spec)
    return expanded

def fetch_and_validate_registry(
    url: str,
    filename: str,
    force_local_env_key: str,
    registry_name: str = "Registry",
    min_count: int = 0,
    parser_hook: Optional[Callable[[dict], dict]] = None,
) -> Tuple[dict, dict]:
    """
    범용 Fetcher: URL 조회 -> (성공 시) 로컬 백업 & 파싱 -> (실패 시) 로컬 로드 & 파싱
    """
    source_info = {"source": "local", "url": url, "is_env_forced": False, "fallback_reason": None}
    
    # 강제 로컬 로드 환경변수 확인
    if os.getenv(force_local_env_key, "").lower() == "true":
        source_info["is_env_forced"] = True
        local_data = load_local_backup(filename)
        return (parser_hook(local_data) if parser_hook else local_data), source_info

    try:
        # 원격 패치
        response = httpx.get(url, timeout=5)
        response.raise_for_status()
        content = response.json()
        
        # 무결성 검증
        if not isinstance(content, dict) or len(content) < min_count:
            raise ValueError(f"Invalid map format or item count less than min_count({min_count})")

        # 성공 시 로컬 백업 파일 최신화
        save_local_backup(content, filename)
        
        source_info["source"] = "remote"
        return (parser_hook(content) if parser_hook else content), source_info

    except Exception as e:
        # 실패 시 즉각 로컬 백업 폴백
        log.warning(f"[{registry_name}] Failed to fetch remote map. Falling back to local: {e}")
        source_info["fallback_reason"] = str(e)
        local_data = load_local_backup(filename)
        return (parser_hook(local_data) if parser_hook else local_data), source_info

# ---------------------------------------------------------
# 4. Public Endpoints (외부 호출용 Facade)
# ---------------------------------------------------------
def get_model_cost_map(url: str) -> Tuple[dict, dict]:
    return fetch_and_validate_registry(
        url=url,
        filename="model_prices_and_context_window_backup.json",
        force_local_env_key="LITELLM_LOCAL_MODEL_COST_MAP",
        registry_name="ModelCostMap",
        min_count=50,
        parser_hook=parse_model_cost_map
    )

def get_provider_endpoints_map(url: str) -> Tuple[dict, dict]:
    return fetch_and_validate_registry(
        url=url,
        filename="provider_endpoints_support_backup.json",
        force_local_env_key="LITELLM_LOCAL_PROVIDER_ENDPOINTS",
        registry_name="ProviderEndpoints",
        min_count=5,
        parser_hook=None
    )