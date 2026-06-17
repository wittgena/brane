# phase.bind.redirector
## @lineage: gov.router.module.redirector
import sys
import importlib.util
from pathlib import Path
from typing import Optional, Union
from phase.bind.resolver import find_current_self

SELF_ROOT = find_current_self()

class ModuleRedirector:
    def __init__(self, target_package: str, local_dir: Union[str, Path], clear_cache: bool = True):
        self.target_package = target_package
        self.local_dir = Path(local_dir).resolve()
        self.clear_cache = clear_cache
        self._is_installed = False

    def find_spec(self, fullname, path, target=None):
        ## 대상 패키지 또는 그 하위 패키지인지 확인
        if fullname == self.target_package or fullname.startswith(f"{self.target_package}."):
            rel_path = fullname[len(self.target_package):].lstrip(".").replace(".", "/")
            target_path = self.local_dir / rel_path

            ## 패키지 형태 (__init__.py 존재) 확인
            if target_path.is_dir():
                init_file = target_path / "__init__.py"
                if init_file.exists():
                    return importlib.util.spec_from_file_location(
                        fullname,
                        str(init_file),
                        submodule_search_locations=[str(target_path)]
                    )
            
            ## 단일 파일 형태 (.py 존재) 확인
            py_file = target_path.with_suffix(".py")
            if py_file.exists():
                return importlib.util.spec_from_file_location(fullname, str(py_file))

        return None

    def install(self):
        """커스텀 파인더를 sys.meta_path의 최우선 순위로 등록"""
        if self._is_installed:
            return

        if self.clear_cache:
            self._clear_sys_modules()

        sys.meta_path.insert(0, self)
        self._is_installed = True
        print(f"[Redirector] '{self.target_package}' -> '{self.local_dir}' mapping installed.")

    def uninstall(self):
        """등록된 커스텀 파인더를 제거"""
        if self in sys.meta_path:
            sys.meta_path.remove(self)
        
        if self.clear_cache:
            self._clear_sys_modules()
            
        self._is_installed = False
        print(f"[Redirector] '{self.target_package}' mapping uninstalled.")

    def _clear_sys_modules(self):
        """기존에 로드된 캐시 모듈을 삭제하여 재로드를 강제"""
        keys_to_del = [
            key for key in sys.modules.keys() 
            if key == self.target_package or key.startswith(f"{self.target_package}.")
        ]
        for key in keys_to_del:
            del sys.modules[key]

    ## 컨텍스트 매니저 지원 (with 문 사용 가능)
    def __enter__(self):
        self.install()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.uninstall()

class PhaseAirlock:
    """
    @desc: 위상 경계(Boundary)에서 발생하는 네임스페이스 분열을 제어하는 에어록 장치
    과거의 레거시 경로(Legacy)를 현재의 정규 위상(Canonical)으로 메모리 상에서 강제 동기화
    """

    @classmethod
    def establish_resonance(cls, legacy_path: str, canonical_path: str, submodules: list[str] = None):
        """
        sys.modules를 조작하여 두 네임스페이스의 메모리 ID를 일치 (분열 방지)
        Args:
            legacy_path: 외부 패키지가 찾으려고 시도하는 과거의 경로 (예: "tool")
            canonical_path: 현재 시스템의 진짜 물리적 경로
            submodules: 함께 묶어줄 하위 모듈 이름의 리스트
        """
        try:
            ## 진짜 위상(Canonical)을 메모리에 로드
            canonical_module = importlib.import_module(canonical_path)
            
            ## 과거의 궤적(Legacy)에 진짜 위상을 덮어쓰기
            sys.modules[legacy_path] = canonical_module
            log.info(f"[*] Resonance Established: {legacy_path} ➔ {canonical_path}")
            
            ## 명시된 하위 모듈들 동기화 (Pydantic 검증 우회를 위해 필수적임)
            if submodules:
                for sub in submodules:
                    target_sub_path = f"{canonical_path}.{sub}"
                    legacy_sub_path = f"{legacy_path}.{sub}"
                    
                    target_sub_module = importlib.import_module(target_sub_path)
                    sys.modules[legacy_sub_path] = target_sub_module
                    log.info(f"    ↳ Linked Submodule: {legacy_sub_path} ➔ {target_sub_path}")
                    
        except ImportError as e:
            log.error(f"[!] PhaseAirlock Failed: 정규 위상({canonical_path})을 로드할 수 없습니다. {e}")
            raise
