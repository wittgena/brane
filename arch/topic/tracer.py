# arch.topic.tracer
## @lineage: arch.model.topic.tracer
## @lineage: arch.project.topic.tracer
"""
@flow:
- TopicMap(위상 지도) 기반 목표 모듈 식별
- 동적 임포트(Import) 및 심볼(Callable) 추출
- strike(): Φ -> ∂Φ (reflective injection) -> rupture -> traces
- ExtRegistry에 결과 결속 (Assimilate)
"""
import os
import ast
import inspect
import importlib
import sys
import signal
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Any, Dict, List, Optional
from arch.topic.registry import TopicRegistry, TopicMap
from watcher.plane.emitter import get_emitter

log = get_emitter('topic.tracer')

class TemporalRupture(Exception):
    """@role: 무한 루프나 블로킹 코드를 끊어내는 위상적 시간 한계 예외"""
    pass

class TopologicalRupture(Exception):
    """@role: 순환 참조 등 구조적 붕괴 상태 예외"""
    pass


@contextmanager
def time_limit(seconds: int):
    """@flow: 시간 제한 장(Field) 형성 -> 한계 도달 시 강제 Rupture 격발"""
    def signal_handler(signum, frame):
        raise TemporalRupture(f"Execution exceeded temporal limit of {seconds}s.")
    
    # 알람 시그널 바인딩 및 타이머 시작
    old_handler = signal.signal(signal.SIGALRM, signal_handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        # 정상 종료 시 타이머 해제 및 핸들러 복구
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)

class TraceReflector:
    """@flow: access → ∂Φ trace"""
    def __init__(self, trace_log: List[str], path: str = "root"):
        self._trace_log = trace_log
        self._path = path

    def _log_and_rupture(self, action: str):
        current_path = f"{self._path} -> {action}"
        self._trace_log.append(current_path)
        raise RuntimeError(f"round.rupture: {current_path}")

    def __getattr__(self, name): self._log_and_rupture(f"getattr(.{name})")
    def __call__(self, *args, **kwargs): self._log_and_rupture("call()")
    def __getitem__(self, key): self._log_and_rupture(f"getitem([{key}])")
    def __iter__(self): self._log_and_rupture("iter()")

    # [핵심 교정] 파이썬 내장 객체 변환 완벽 통제 (디스크 오염 방지)
    def __str__(self): return "TRACE_REFLECTOR_MOCK"
    def __repr__(self): return "TRACE_REFLECTOR_MOCK"
    def __fspath__(self): 
        # os.makedirs, Path() 등의 물리적 경로 변환 시도시 즉각 파열
        self._log_and_rupture("fspath()")
    def __bool__(self): return False


# --- [ 교정 2 ] 파이썬의 암묵적 패키지 초기화(__init__) 위상 연결 ---
class TopologicalCycleDetector:
    """@phi: 런타임 붕괴 전 AST 구조만으로 순환 위상(Closed Loop)을 탐지"""
    NOISE_BOUNDARIES = {".venv", "venv", "__pycache__", ".git", "build", "dist", "node_modules", ".idea"}

    def __init__(self, target_path: Path):
        self.target_path = target_path
        self.graph: Dict[str, Set[str]] = defaultdict(set)
        self.internal_modules: Set[str] = set()
        self._build_topology()

    def _path_to_module(self, path: Path) -> str:
        rel_path = path.relative_to(self.target_path)
        if path.name == "__init__.py":
            return ".".join(rel_path.parent.parts)
        return ".".join(rel_path.with_suffix("").parts)

    def _resolve_import(self, py_file: Path, node: ast.ImportFrom) -> List[str]:
        res = []
        if node.level > 0:
            base_parts = py_file.parent.relative_to(self.target_path).parts
            if node.level > 1:
                base_parts = base_parts[:-(node.level - 1)]
            base_pkg = ".".join(base_parts)
            module_base = f"{base_pkg}.{node.module}" if node.module else base_pkg
        else:
            module_base = node.module or ""

        if module_base:
            # [핵심 교정] A.B.C 임포트 시, A, A.B, A.B.C 모두 의존성으로 추가
            # 파이썬은 A.B.C를 로드하기 위해 A/__init__.py와 A/B/__init__.py를 무조건 실행함
            parts = module_base.split('.')
            for i in range(1, len(parts) + 1):
                res.append(".".join(parts[:i]))

        for alias in node.names:
            if module_base:
                res.append(f"{module_base}.{alias.name}")
            else:
                res.append(alias.name)
        return res

    def _build_topology(self):
        for py_file in self.target_path.rglob("*.py"):
            if any(part in self.NOISE_BOUNDARIES for part in py_file.parts):
                continue

            mod_name = self._path_to_module(py_file)
            if not mod_name: continue
            self.internal_modules.add(mod_name)
            
            try:
                tree = ast.parse(py_file.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            # [핵심 교정] import A.B.C 도 동일하게 계층 구조 추가
                            parts = alias.name.split('.')
                            for i in range(1, len(parts) + 1):
                                self.graph[mod_name].add(".".join(parts[:i]))
                    elif isinstance(node, ast.ImportFrom):
                        for resolved_path in self._resolve_import(py_file, node):
                            self.graph[mod_name].add(resolved_path)
            except Exception:
                pass

    def detect_cycles(self) -> List[List[str]]:
        visited = set()
        visiting = set()
        path = []
        cycles = []

        def dfs(node: str):
            if node not in self.internal_modules: return
            if node in visiting:
                cycle_start = path.index(node)
                cycles.append(path[cycle_start:] + [node])
                return
            if node in visited: return

            visiting.add(node)
            path.append(node)
            for neighbor in self.graph.get(node, set()):
                dfs(neighbor)
            visiting.remove(node)
            visited.add(node)
            path.pop()

        for mod in sorted(self.internal_modules):
            if mod not in visited:
                dfs(mod)
                
        # 가장 근원적인 순환참조부터 리포팅하기 위해 길이순 정렬
        cycles.sort(key=len)
        return cycles

class ExceptionSnapshot:
    """@flow: exception → stack + locals"""
    @staticmethod
    def capture(e: Exception) -> Dict[str, Any]:
        snapshot = {"error": f"{type(e).__name__}: {str(e)}", "stack": []}
        tb = e.__traceback__
        while tb:
            frame = tb.tb_frame
            if "tool/binder" not in frame.f_code.co_filename:
                snapshot["stack"].append({
                    "function": frame.f_code.co_name,
                    "line": tb.tb_lineno,
                    "locals": {k: str(v)[:60] for k, v in frame.f_locals.items() if not k.startswith("__")}
                })
            tb = tb.tb_next
        return snapshot

class TopicTracer:
    """@flow: StaticScan(Quarantine) -> TargetScan -> Registry"""
    def __init__(self, topic_map: Optional[TopicMap] = None):
        self.topic_map = topic_map
        self.registry = TopicRegistry()
        self.ruptured_modules: Set[str] = set()

    @staticmethod
    def probe(target: Callable) -> Dict[str, Any]:
        """기존의 파괴적 경계면 탐색 로직 (단일 대상)"""
        echoes = {"signature": None, "traces": [], "behavioral_map": {}}
        
        try:
            sig = inspect.signature(target)
            echoes["signature"] = str(sig)
        except (ValueError, TypeError) as e:
            echoes["traces"].append(f"[SigFail] {e}")
            return echoes

        access_log = []
        try:
            args, kwargs = [], {}
            for name, param in sig.parameters.items():
                reflector = TraceReflector(access_log, path=f"param({name})")
                if param.kind == inspect.Parameter.KEYWORD_ONLY:
                    kwargs[name] = reflector
                else:
                    args.append(reflector)
            
            target(*args, **kwargs)
        except Exception as e:
            echoes["traces"].append(f"[exception] {type(e).__name__}")
            echoes["behavioral_map"] = {
                "access_path": access_log,
                "snapshot": ExceptionSnapshot.capture(e)
            }
            
        return echoes

    def run_strategic_scan(self, target_path: Path):
        """위상 지도를 바탕으로 탐침. 단, 순환참조 검역을 우선 수행합니다."""
        if not self.topic_map:
            log.info("[!] TopicMap이 누락되었습니다. 스캔을 건너뜁니다.")
            return

        # 1. [검역소: Quarantine] 정적 위상 검사
        log.info("\n[Tracer:Quarantine] 🔍 Scanning for Topological Cycles (AST)...")
        detector = TopologicalCycleDetector(target_path)
        cycles = detector.detect_cycles()
        
        if cycles:
            log.info("[Tracer:Quarantine] 🚨 [Rupture Warning] 치명적인 순환 참조 감지됨!")
            for idx, cycle in enumerate(cycles, 1):
                loop_path = " ➔ ".join(cycle)
                log.info(f"   [{idx}] {loop_path}")
                for mod in cycle:
                    self.ruptured_modules.add(mod)
            log.info(f"[Tracer:Quarantine] 🛑 붕괴 위험이 있는 {len(self.ruptured_modules)}개 모듈은 프로빙(동적 붕괴)에서 제외됩니다.\n")
        else:
            log.info("[Tracer:Quarantine] ✅ 위상 흐름이 안정적입니다. 순환 참조 없음.\n")

        # 2. [물리적 프로빙]
        sys.path.insert(0, str(target_path.absolute()))
        original_argv = sys.argv.copy()
        
        try:
            for phase_id, phase_space in self.topic_map.spaces.items():
                for core_module in phase_space.core_modules:
                    module_name = core_module.path.replace('\\', '/').replace('/', '.').replace('.py', '')

                    # 순환 참조로 오염된 모듈은 동적 임포트(Collapse) 생략
                    if module_name in self.ruptured_modules:
                        log.info(f"[Bounder:Scan] ⏭️ Skipping ruptured module: {module_name}")
                        continue

                    try:
                        sys.argv = [original_argv[0]] 
                        with time_limit(3):
                            module = importlib.import_module(module_name)
                            
                            for name, obj in inspect.getmembers(module):
                                if callable(obj) and getattr(obj, '__module__', None) == module_name and not name.startswith('_'):
                                    echoes = self.probe(obj)
                                    self.registry.assimilate(module_name, name, echoes)
                                    
                    except TemporalRupture as e:
                        log.info(f"[Bounder:Scan] 🚨 [Rupture] Infinite Loop isolated in '{module_name}'.")
                    except Exception as e:
                        log.info(f"[Bounder:Scan] Module Load Failed ({module_name}): {type(e).__name__} - {e}")
                    finally:
                        sys.argv = original_argv
        finally:
            sys.path.pop(0)
            sys.argv = original_argv
