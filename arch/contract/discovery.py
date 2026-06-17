# arch.contract.discovery
## @lineage: arch.contract.discover
import sys
import importlib
import ast
from pathlib import Path
from typing import Optional, Set
from phase.bind.resolver import load_bound, find_current_self

SAFE_TOP_LEVEL_CALLS = {
    "get_logger", "get_emitter", "resolve_path", "find_current_self", "Path", "os.getenv", 
    "load_dotenv", "dict", "set", "list", "tuple", "SynapticRouter"
}

def _has_top_level_side_effects(py_file: Path) -> bool:
    """@internal: 모듈 임포트 시 원치 않는 코드가 즉시 실행되는지 AST로 검사."""
    try:
        with open(py_file, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=py_file.name)
            
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            
            if isinstance(node, ast.Assign):
                if isinstance(node.value, ast.Call):
                    func_name = ""
                    if isinstance(node.value.func, ast.Name):
                        func_name = node.value.func.id
                    elif isinstance(node.value.func, ast.Attribute):
                        func_name = f"{node.value.func.value.id}.{node.value.func.attr}" if isinstance(node.value.func.value, ast.Name) else node.value.func.attr
                    
                    if func_name in SAFE_TOP_LEVEL_CALLS:
                        continue
                    else:
                        return True 
                continue

            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                continue
            
            if isinstance(node, ast.If):
                test = node.test
                if isinstance(test, ast.Compare):
                    left = test.left
                    if isinstance(left, ast.Name) and left.id == "__name__":
                        continue

            return True
            
    except Exception as e:
        print(f"[Discover] AST Side-effect Check failed for {py_file.name}: {e}")
        return True 

    return False

def _contains_forbidden_imports(py_file: Path, forbidden_libs: Set[str]) -> bool:
    """@internal: 특정 외부 패키지를 참조하는지 정적으로 검사"""
    if not forbidden_libs:
        return False
        
    try:
        with open(py_file, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=py_file.name)
            
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_module = alias.name.split('.')[0]
                    if root_module in forbidden_libs:
                        return True
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    root_module = node.module.split('.')[0]
                    if root_module in forbidden_libs:
                        return True
    except Exception as e:
        print(f"[Discover] AST Parsing failed for {py_file.name}: {e}")
        return False

    return False

def discover_modules(
    root: Path, 
    forbidden_libs: Optional[Set[str]] = None,
    exclude_files: Optional[Set[str]] = None,
    force_reload: bool = False
) -> None:
    if not root.exists():
        print(f"[Discover] Root path {root} does not exist.")
        return
    
    ## 1. 사전에 bound.json을 로드하여 '특권 레포지토리의 절대 경로 목록'을 캐싱
    core_paths = []
    try:
        self_root = find_current_self(root)
        bound_data = load_bound(self_root)
        around_data = bound_data.get("around", {})
        
        for repo_name, repo_info in around_data.items():
            if repo_info.get("allow_side_effects", False):
                repo_abs_path = repo_info.get("path")
                if repo_abs_path:
                    core_paths.append((repo_name, repo_abs_path))
    except Exception as e:
        print(f"[Discover] Bound loading failed, applying strict rules: {e}")

    print(f"[Discover] Start module discovery from: {root}")
    if core_paths:
        print(f"[Discover] Active Core Repos (Bypassing side-effects): {[name for name, _ in core_paths]}")

    forbidden_set = forbidden_libs or ["dspy"]
    exclude_set = exclude_files or {"registry.py", "scanner.py", "discover.py"}

    root_path_str = str(root.resolve())
    if root_path_str not in sys.path:
        sys.path.insert(0, root_path_str)

    for py_file in root.rglob("*.py"):
        ## 로깅용 상대 경로
        try:
            rel_path_str = str(py_file.relative_to(root.parent))
        except ValueError:
            rel_path_str = str(py_file.name)

        if (py_file.name.startswith("_") and py_file.name != "__init__.py") or \
           py_file.name in exclude_set:
            continue

        if _contains_forbidden_imports(py_file, forbidden_set):
            print(f"[Discover] Ignored (Heavy Dependency) : {rel_path_str}")
            continue

        ## 개별 파일의 절대 경로를 검사하여 특권 레포지토리에 속하는지 판별
        abs_py_file = str(py_file.resolve())
        is_core_file = False
        repo_label = "Periphery"
        
        for repo_name, core_path in core_paths:
            # 파일 경로가 특권 레포지토리 경로로 시작하면 권한 면제
            if abs_py_file.startswith(core_path):
                is_core_file = True
                repo_label = repo_name
                break

        ## @rule.C: 최상단 부수 효과 원천 차단 (특권이 없는 경우에만)
        if not is_core_file:
            if _has_top_level_side_effects(py_file):
                print(f"[Discover] Ignored (Top-level Side-effects) : {rel_path_str}")
                continue

        ## @rule.D: 모듈 동적 로딩
        try:
            relative = py_file.relative_to(root)
            module_path = ".".join(relative.with_suffix("").parts)
            if module_path:
                if module_path in sys.modules:
                    if force_reload:
                        importlib.reload(sys.modules[module_path])
                else:
                    importlib.import_module(module_path)
        except Exception as e:
            print(f"[Discover] Failed to load {rel_path_str}: {e}")