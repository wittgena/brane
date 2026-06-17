# watcher.plane.sieve
## @lineage: phase.plane.sieve
"""
@internal: semantic sieve
@desc: 3rd-party의 side effect와 I/O 소음을 선언적으로 차단
"""
import os
import sys
import logging
import warnings
import importlib
from contextlib import contextmanager
from typing import Dict, List, Set, Any

NOISE_PROFILES = {
    "litellm": {
        "env": {
            "LITELLM_LOG": "ERROR",
            "SUPPRESS_LITELLM_LOGS": "True",
            "OPENAI_LOG": "ERROR",
            "ANONYMIZED_TELEMETRY": "False"
        },
        "loggers": ["litellm", "LiteLLM"],
        "warnings_module": "litellm",
        "pre_import": True,  # 선제적 격리 대상 여부
        "signatures": ["Provider List:", "https://docs.litellm.ai"] # 동적 필터링 키워드
    },
    "http": {
        "loggers": ["httpx", "httpcore", "urllib3", "httpcore.connection", "httpcore.http11"],
    },
    "huggingface": {
        "env": {"HF_HUB_DISABLE_TELEMETRY": "1", "TF_CPP_MIN_LOG_LEVEL": "3"},
        "loggers": ["transformers", "huggingface_hub"],
    }
}

class SemanticSieve:
    """stdout 스트림을 가로채어 등록된 시그니처만 걸러내는 물리적 체(Sieve)"""
    def __init__(self, original_stream, signatures: Set[str]):
        self.original = original_stream
        self.signatures = signatures

    def write(self, msg):
        if any(sig in msg for sig in self.signatures):
            return # 노이즈 증발
        self.original.write(msg)

    def flush(self):
        self.original.flush()

class SemanticSieve:
    def __init__(self, profiles: Dict[str, Dict[str, Any]]):
        self.profiles = profiles
        self.blackhole = logging.NullHandler()
        
        # 전체 시그니처 집계
        self.global_signatures = set()
        for p in self.profiles.values():
            self.global_signatures.update(p.get("signatures", []))

    def _apply_env_overrides(self):
        for profile in self.profiles.values():
            env_vars = profile.get("env", {})
            for k, v in env_vars.items():
                os.environ[k] = v

    def _hijack_loggers(self):
        for profile in self.profiles.values():
            for logger_name in profile.get("loggers", []):
                logger = logging.getLogger(logger_name)
                logger.setLevel(logging.ERROR)
                logger.propagate = False
                if not logger.handlers:
                    logger.addHandler(self.blackhole)

            warn_mod = profile.get("warnings_module")
            if warn_mod:
                warnings.filterwarnings("ignore", module=warn_mod)

    @contextmanager
    def vacuum_chamber(self):
        """완전 진공 상태: 임포트 시점의 1회성 악성 부수 효과 흡수용"""
        with open(os.devnull, "w") as devnull:
            old_stdout, old_stderr = sys.stdout, sys.stderr
            sys.stdout, sys.stderr = devnull, devnull
            try:
                yield
            finally:
                sys.stdout, sys.stderr = old_stdout, old_stderr

    @contextmanager
    def dynamic_filter(self):
        """런타임 의미론적 체: 특정 시그니처만 차단하고 나머지는 통과"""
        if not self.global_signatures:
            yield
            return
            
        old_stdout = sys.stdout
        sys.stdout = SemanticSieve(old_stdout, self.global_signatures)
        try:
            yield
        finally:
            sys.stdout = old_stdout

    def _quarantine_imports(self):
        """pre_import가 설정된 모듈을 진공 챔버 안에서 강제 기폭시킵니다."""
        with self.vacuum_chamber():
            for mod_name, profile in self.profiles.items():
                if profile.get("pre_import"):
                    try:
                        importlib.import_module(mod_name)
                    except ImportError:
                        pass

    def deploy(self):
        """막(Sieve) 전개: 환경 -> 로거 -> 격리 임포트 순으로 시스템을 장악합니다."""
        self._apply_env_overrides()
        self._hijack_loggers()
        self._quarantine_imports()


sieve = SemanticSieve(NOISE_PROFILES)
sieve.deploy()
apply_semantic_sieve = sieve.dynamic_filter