# phase.ator.activator
## @lineage: phase.activator.bootstrap
## @lineage: phase.bind.activator.bootstrap
"""@flow: Φ₀ (physical) -> Workspace Setup (pth) -> Dynamic Discovery -> Manifold Bootstrap (Φ*)"""
import sys
import subprocess
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Any

C_BLUE = "\033[94m"
C_GREEN = "\033[92m"
C_WARN = "\033[93m"
C_ERR = "\033[91m"
C_END = "\033[0m"

class Activator:
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.self_dir = self.workspace
        self.registry: Any = None
        self.log: Any = None

    def _setup_physical_boundary(self):
        """@phase: physical boundary acquisition & path linking"""
        print(f"\n## @phase.repo: Physical Workspace Acquisition")
        ## 탐색 후보지 설정 (우선순위: 정착된 anchor -> 초기 원본 meta/anchor)
        candidates = [
            self.self_dir / "anchor" / "around.py",
            self.self_dir / "meta" / "anchor" / "around.py"
        ]

        ## 존재하는 스크립트 경로 확정
        pth_script = None
        for candidate in candidates:
            if candidate.exists():
                pth_script = candidate
                break
        
        if pth_script.exists():
            print(f"{C_GREEN}[exec] python {pth_script}{C_END}")
            subprocess.run([sys.executable, str(pth_script)], cwd=self.self_dir, check=True)
        else:
            print(f"{C_WARN}[skip] pth.py를 찾을 수 없습니다. 환경에 따라 건너뜁니다.{C_END}")

    def run_bootstrap_sequence(self, group_order: List[str]):
        """인스턴스에 등록된 registry를 사용하여 시퀀스 실행"""
        if self.registry is None:
            raise RuntimeError("Registry가 초기화되지 않았습니다. execute()를 먼저 호출하세요.")

        print(f"\n## Dynamic Subprocess Bootstrap ")
        for group in group_order:
            print(f"\n## @phase.group: {group}")
            
            # [수정] phase_name -> group (루프 변수와 일치화)
            suggest_targets = self.registry.registered_cli_tasks.get(group, [])
            targets = [t for t in suggest_targets if "bootstrap" in t.get("tags", [])]

            if not targets:
                # [수정] phase_name -> group
                print(f"  └── (No bootstrap scripts registered for '{group}')")
                continue

            for target in targets:
                module_fqn = target["module_fqn"]
                cli_args = target["args"]
                
                # -m 옵션을 사용하여 모듈 단위로 실행
                cmd = [sys.executable, "-m", module_fqn] + cli_args
                print(f"  └── {C_GREEN}[exec] {' '.join(cmd)}{C_END}")
                
                try:
                    # check=True로 설정되어 있으므로 실패 시 에러 발생
                    subprocess.run(cmd, cwd=self.self_dir, check=True, text=True)
                except subprocess.CalledProcessError as e:
                    print(f"{C_ERR}[fatal] Bootstrap execution failed: {module_fqn} (Exit Code: {e.returncode}){C_END}")
                    sys.exit(1)

    def execute(self):
        """@orchestration: ordered phase traversal"""
        try:
            ## pth 초기화 (물리적 경로 확보)
            self._setup_physical_boundary()

            ## 동적 임포트 (통합 레지스트리로 변경)
            from watcher.plane.emitter import get_emitter
            from arch.contract.registry.unified import registry
            from arch.contract.discovery import discover_modules
            from phase.bind.resolver import load_bound, find_current_self
            
            self.registry = registry
            self.log = get_emitter("in.activator")

            ## 모듈 스캔 및 등록
            print(f"\n{C_BLUE}--- Traversing Modules for Contract Discovery ---{C_END}")
            # 탐색 디렉토리는 환경에 맞게 조정 (기존 repo 구조 반영)
            repos = load_bound(find_current_self()).get('around')
            self.log.info(f"repos: {repos}")
            for repo in repos: 
                repo_path = self.self_dir / repo
                if repo_path.exists():
                    # 스캔하면서 @manifold_contract와 @bootstrap_contract가 registry에 누적됨
                    discover_modules(repo_path)

            ## 시퀀스 실행
            phase_order = [
                "sensor_ready", 
                "core_materialized", 
                "topology_mapped",
                "contract_sealed", 
                "overlay_indexed", 
                "invariants_verified"
            ]
            self.run_bootstrap_sequence(phase_order)
            print(f"\n{C_BLUE}[Φ-threshold reached] Activation-ready.{C_END}")
        except Exception as e:
            print(f"\n{C_ERR}[fatal] bootstrap collapse: {e}{C_END}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

if __name__ == "__main__":
    current_workspace = Path.cwd() 
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Phase Bootstrap Sequence Initiated...")
    
    ator = Activator(workspace=current_workspace)
    ator.execute()