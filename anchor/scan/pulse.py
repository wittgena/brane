# anchor.scan.pulse
## @lineage: bound.scan.pulse
## @lineage: debug.exam.scan.pulse
## @lineage: meta.flow.scan.pulse
import os
import sys
import argparse
import re
from typing import List, Dict, Tuple
from pathlib import Path
from phase.bind.resolver import find_current_self
from arch.contract.registry.unified import contract
from watcher.plane.emitter import get_emitter
from phase.runtime.cli.executor import CliTaskAdapter, dispatch_cli, parse_local

log = get_emitter("scan.pulse")

try:
    SELF_ROOT = find_current_self()
except Exception as e:
    log.error(f"[error] 기준면(.self)을 찾을 수 없음: {e}")
    sys.exit(1)

TARGET_EXTENSIONS = {".md", ".py", ".kt"}
EXCLUDED_DIRS = {"__pycache__"}

FILE_FORMATS = {
    ".md": {"title": "# ",  "lineage": "@lineage:"},
    ".py": {"title": "# ",  "lineage": "## @lineage:"},
    ".kt": {"title": "// ", "lineage": "// @lineage:"},
}

class PhaseState:
    CONVERGED = "🟢 [Attractor] 수렴됨 (에너지 안정 상태)"
    OSCILLATING = "🔴 [Rupture] 진동 중 (해결되지 않은 위상적 장력 / xe 발생지점)"
    MUTATING = "🔵 [Frontline] 활성 변이 (문명과의 마찰 최전선)"

class TrajectoryNode:
    def __init__(self, filename: str, lineages: List[str]):
        self.filename = filename
        self.lineages = lineages
        self.tension_score = 0.0
        self.state = None
        self.analyze_trajectory()

    def analyze_trajectory(self):
        """@lineage의 변화 패턴을 분석하여 파일의 현재 위상 상태와 장력(∇Φ)을 계산"""
        if not self.lineages:
            self.state = PhaseState.CONVERGED
            return

        recent_history = self.lineages[-5:]
        unique_states = list(dict.fromkeys(recent_history))
        
        ## 진동 (Oscillation): A -> B -> A -> B
        if len(recent_history) > 2 and len(unique_states) <= 2 and recent_history[0] != recent_history[-1]:
            self.state = PhaseState.OSCILLATING
            self.tension_score = 0.8 + (len(recent_history) * 0.05)
            
        ## 수렴 (Convergence): A -> A.b -> A.b.c (안착)
        elif len(set(recent_history[-2:])) == 1:
            self.state = PhaseState.CONVERGED
            self.tension_score = 0.0
            
        ## 고빈도 변이 (Mutation): A -> B -> C -> D
        else:
            self.state = PhaseState.MUTATING
            self.tension_score = 0.3

class PulseScanner:
    """phenotype.to.genotype - 실제 파일의 헤더를 스캔하여 기울기(∇Φ) 측정"""
    def __init__(self, root_dir: str):
        self.root_dir = Path(root_dir)
        self.registry: Dict[str, TrajectoryNode] = {}

    def scan(self, only_dirs: List[str] | None = None):
        """실제 파일 시스템에서 @lineage를 수집하여 궤적 생성"""
        log.info(f"[scan.pulse] start (root={self.root_dir})")
        
        try:
            repo_dirs = [
                d for d in self.root_dir.iterdir()
                if d.is_dir()
                and not d.name.startswith(".")
                and d.name not in EXCLUDED_DIRS
                and (only_dirs is None or d.name in only_dirs)
            ]
        except FileNotFoundError:
            log.error(f"[error] 루트 디렉토리 '{self.root_dir}'를 찾을 수 없습니다.")
            return

        for repo_dir in repo_dirs:
            for file_path in repo_dir.rglob("*"):
                if (
                    not file_path.is_file()
                    or file_path.suffix not in TARGET_EXTENSIONS
                    or file_path.name.startswith(".")
                    or any(p in EXCLUDED_DIRS for p in file_path.parts)
                ):
                    continue

                self._ingest_file(file_path, repo_dir)

    def _ingest_file(self, file_path: Path, repo_dir: Path):
        """단일 파일의 위상 헤더를 분석하여 Lineage 히스토리를 추출"""
        ext = file_path.suffix
        fmt = FILE_FORMATS.get(ext, FILE_FORMATS[".md"])
        title_prefix = fmt["title"]

        try:
            with file_path.open("r", encoding="utf-8") as f:
                lines = f.readlines()

            if not lines:
                return

            first_line = lines[0].strip()
            if not first_line.startswith(title_prefix):
                return

            # 현재 상태 (Namespace) 추출
            current_namespace = first_line[len(title_prefix):].strip()
            if not re.match(r'^[\w\.\-]+$', current_namespace):
                return

            # 과거 @lineage 추출 (헤더 영역 내에서만 파싱)
            lineages = []
            for line in lines[1:]:
                stripped = line.strip()
                if "@lineage:" in stripped:
                    val = stripped.split("@lineage:")[-1].strip()
                    if val and val not in lineages:
                        lineages.append(val)
                elif stripped.startswith(title_prefix):
                    continue  # 중복 타이틀 무시
                else:
                    break  # 일반 코드가 나오면 헤더 종료로 간주

            ## 최상단에 쌓이는 과거 계보를 시간순(과거->현재)으로 정렬하기 위해 reverse 적용 후 현재 상태 추가
            history = lineages[::-1] + [current_namespace]
            relative_name = file_path.relative_to(self.root_dir).as_posix()
            self.registry[relative_name] = TrajectoryNode(relative_name, history)
        except Exception as e:
            log.error(f"[error] {file_path}: {e}")

    def generate_report(self):
        """시스템 전체의 위상 지도를 출력"""
        log.info("\n" + "="*60)
        log.info(" [PULSE] Topological Tension Scan Report")
        log.info("="*60)

        total_tension = 0
        rupture_spots = []

        if not self.registry:
            log.info("스캔된 파일/궤적이 없습니다.")
            return

        for filename, node in self.registry.items():
            total_tension += node.tension_score
            current_lineage = node.lineages[-1] if node.lineages else "Unknown"
            
            log.info(f"{filename}")
            log.info(f"   ├─ Lineage: {current_lineage}")
            log.info(f"   ├─ State  : {node.state}")
            log.info(f"   └─ Tension: {node.tension_score:.2f}\n")

            if node.state == PhaseState.OSCILLATING:
                rupture_spots.append((filename, node.lineages[-3:]))

        system_stability = 100 - (min(total_tension / len(self.registry) * 100, 100))
        
        log.info("-" * 60)
        log.info(f"[System Stability]: {system_stability:.1f}%")
        
        if rupture_spots:
            log.warning("\n[Action Required] 위상 진동(Oscillation) 감지됨!")
            for spot, trace in rupture_spots:
                log.warning(f"   - {spot} 이 두 위상 사이에서 갇혀 있습니다: {trace}")
                log.warning("     -> ResonanceAligner 를 가동하여 이 의존성의 기울기를 해소하십시오")
        else:
            log.info("\n시스템이 완벽한 Attractor에 수렴")

    def run(self, only_dirs: List[str] | None = None):
        self.scan(only_dirs)
        self.generate_report()
        return True


def entry_task(args):
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", action="append", help="스캔할 대상 디렉토리 (예: --repo meta --repo theoria)")
    args = parser.parse_args(args)
    scanner = PulseScanner(SELF_ROOT)
    run_kwargs = {
        "only_dirs": args.repo or None
    }
    return CliTaskAdapter(scanner.run, **run_kwargs)

@contract.cli(name="scan.pulse", recept=[])
def main():
    bound_args, remain = parse_local(sys.argv[1:])
    if bound_args.local:
        entry_task(remain).run()
    else:
        dispatch_cli("scan.pulse", entry_task, __file__)

if __name__ == "__main__":
    main()