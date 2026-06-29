# anchor.surface.provider.freetier.registry
import json
import time
from pathlib import Path
from collections import deque
from typing import Dict, List, Optional, Any

from phase.bind.resolver import resolve_path
from watcher.plane.emitter import get_emitter

log = get_emitter("freetier.registry", phase="SYSTEM")

MANIFEST_PATH = resolve_path("res") / "config" / "free_tier_manifold.json"

class FreeTierQuotaRegistry:
    """
    @manifold: Proactive Rate Limit & Rotation Registry
    @desc: 슬라이딩 윈도우 알고리즘을 사용하여 무료 티어 모델의 RPM을 추적하고, 
           한도 초과가 예상되거나 실제 429 발생 시 모델을 페널티 박스에 격리
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(FreeTierQuotaRegistry, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        self.config: Dict[str, Any] = {}
        self.models: List[Dict[str, Any]] = []
        self.window_seconds = 60
        self.penalty_seconds = 45
        
        # 상태 추적기 (State Trackers)
        # model_name -> deque([timestamp1, timestamp2, ...])
        self.call_history: Dict[str, deque] = {}
        
        # model_name -> 쿨다운 해제 타임스탬프
        self.penalty_box: Dict[str, float] = {}
        
        self.reload_manifest()

    def reload_manifest(self) -> None:
        """JSON 매니페스트를 로드하고 우선순위대로 정렬합니다."""
        if not MANIFEST_PATH.exists():
            log.warning(f"Free tier manifest not found at {MANIFEST_PATH}. Using empty pool.")
            return

        try:
            with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
                self.config = json.load(f)
            
            pool = self.config.get("fallback_pool", [])
            self.models = sorted(pool, key=lambda x: x.get("priority", 99))
            self.window_seconds = self.config.get("window_seconds", 60)
            self.penalty_seconds = self.config.get("default_penalty_seconds", 45)
            
            ## 추적기 초기화
            for m in self.models:
                model_name = m["model"]
                if model_name not in self.call_history:
                    self.call_history[model_name] = deque()
                    
            log.info(f"Loaded {len(self.models)} models into FreeTierQuotaRegistry.")
        except Exception as e:
            log.error(f"Failed to load free tier manifest: {e}")

    def _evict_old_records(self, model_name: str) -> None:
        """슬라이딩 윈도우 밖(예: 60초 이전)의 타임스탬프를 큐에서 제거합니다."""
        history = self.call_history.get(model_name)
        if not history:
            return
            
        current_time = time.time()
        while history and current_time - history[0] > self.window_seconds:
            history.popleft()

    def get_optimal_model(self, requires_tools: bool = False) -> Optional[str]:
        """
        현재 쿼터(RPM)가 남아있고 페널티 상태가 아니며, 요구사항을 충족하는 최적의 모델을 반환합니다.
        """
        current_time = time.time()
        
        for m in self.models:
            model_name = m["model"]
            
            ## 제약 조건 확인 (Tools 지원 여부)
            if requires_tools and not m.get("supports_tools", True):
                continue
                
            ## 페널티 박스 확인 (429 에러 쿨다운 중인지)
            penalty_until = self.penalty_box.get(model_name, 0)
            if current_time < penalty_until:
                continue # 아직 쿨다운 중이므로 스킵
                
            ## RPM 슬라이딩 윈도우 확인
            self._evict_old_records(model_name)
            current_rpm_usage = len(self.call_history[model_name])
            rpm_limit = m.get("rpm_limit", 5)
            
            ## [안전 마진] 구글의 리밋이 엄격하므로 한도에 도달하기 1회 전에 컷오프
            if current_rpm_usage < (rpm_limit - 1):
                return model_name
                
        ## 가용한 모델이 하나도 없는 경우
        log.warning("🚨 All free tier models are currently exhausted or in penalty box.")
        return None

    def record_usage(self, model_name: str) -> None:
        """API 호출 직전에 해당 모델의 호출 타임스탬프를 기록합니다."""
        if model_name in self.call_history:
            self.call_history[model_name].append(time.time())

    def record_failure(self, model_name: str, delay_seconds: Optional[float] = None) -> None:
        """
        실제 429 에러가 발생했을 때 호출됩니다. 
        해당 모델을 지정된 시간(또는 기본 45초) 동안 페널티 박스에 가둡니다.
        """
        penalty_duration = delay_seconds if delay_seconds else self.penalty_seconds
        self.penalty_box[model_name] = time.time() + penalty_duration
        log.warning(f"🚫 Model {model_name} hit 429. Placed in penalty box for {penalty_duration}s.")

freetier_registry = FreeTierQuotaRegistry()