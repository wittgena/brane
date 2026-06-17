# arch.topos.edge.treg
## @lineage: phase.dynamics.edge.treg
## @lineage: arch.dynamics.edge.treg
## @lineage: arch.flow.edge.treg
## @lineage: cognitive.flow.edge.treg
## @lineage: cognitive.edge.treg
## @lineage: cognitive.frame.gate
import time
import hashlib
import argparse
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from arch.topos.edge.trajectory import SignatureBound, TrajectoryXor
from watcher.plane.emitter import get_emitter
from phase.bind.resolver import find_current_self

SELF_ROOT = find_current_self()
log = get_emitter("edge.treg")

# --- [위상 규약] 언어(재질)별 헤더 형식 맵핑 ---
TARGET_EXTENSIONS = {".md", ".py", ".kt"}
FILE_FORMATS = {
    ".md": {"lineage": "@lineage:"},
    ".py": {"lineage": "## @lineage:"},
    ".kt": {"lineage": "// @lineage:"},
}
EXCLUDED_DIRS = {"__pycache__", ".git"}

@dataclass(frozen=True)
class PhaseState:
    """현실과 맞닿은 경계에서의 에너지 및 수용체 파동 (Ψ)"""
    membrane_bound: bool
    axp_ratio: float
    ctla_4_expression: float
    cd28_expression: float
    lineage_path: str

@dataclass(frozen=True)
class FrameLog:
    frame_id: str
    lineage_path: str
    tension_snapshot: float  
    suppress_ratio: float    
    reason: str
    timestamp: float = field(default_factory=time.time)

class FrameRegistry:
    def __init__(self):
        self._frames: List[FrameLog] = []

    def commit_frame(self, lineage: str, tension: float, suppress_ratio: float, reason: str) -> FrameLog:
        raw_id = f"{lineage}:{tension}:{time.time()}"
        frame_id = hashlib.sha256(raw_id.encode()).hexdigest()[:8]
        
        frame = FrameLog(
            frame_id=f"frame.treg.{frame_id}",
            lineage_path=lineage,
            tension_snapshot=tension,
            suppress_ratio=suppress_ratio,
            reason=reason
        )
        self._frames.append(frame)
        log.info(f"[theoria.registry] 닫힘 프레임 등재 완료: {frame.frame_id}")
        log.info(f"  ↳ @lineage: {frame.lineage_path}")
        log.info(f"  ↳ @reason:  {frame.reason}\n")
        return frame

    def get_historical_tension(self, lineage: str) -> float:
        return sum(f.tension_snapshot for f in self._frames if lineage.startswith(f.lineage_path))

class TregEdge:
    TENSION_THRESHOLD = 1.0
    SUPPRESS_DOMINANCE = 0.5
    MEMORY_THRESHOLD = 1.2 

    def __init__(self, registry: FrameRegistry, 
                 signature: Optional[SignatureBound] = None, 
                 xor_engine: Optional[TrajectoryXor] = None):
        self.registry = registry
        self.signature = signature
        self.xor_engine = xor_engine

    def traverse(self, state: PhaseState) -> Dict[str, Any]:
        historical_tension = self.registry.get_historical_tension(state.lineage_path)
        if historical_tension > self.MEMORY_THRESHOLD:
            return {"status": "rejected_by_memory", "message": f"과거 붕괴 이력 누적 (Tension: {historical_tension:.2f})"}

        if state.axp_ratio > self.TENSION_THRESHOLD:
            return self._seal_topology(state, "AxP_saturation_energy_depleted")

        co_stim_ratio = state.ctla_4_expression / max(state.cd28_expression, 0.01)
        if co_stim_ratio > self.SUPPRESS_DOMINANCE:
            return self._seal_topology(state, f"CTLA4_suppression_dominance_{co_stim_ratio:.2f}")

        return {"status": "traversed", "next_node": "phi_x_activation"}

    def _seal_topology(self, state: PhaseState, reason: str) -> Dict[str, Any]:
        frame = self.registry.commit_frame(
            lineage=state.lineage_path,
            tension=state.axp_ratio,
            suppress_ratio=(state.ctla_4_expression / max(state.cd28_expression, 0.01)),
            reason=reason
        )
        
        if self.xor_engine and self.signature:
            synthetic_basis = {
                "lineage": [state.lineage_path],
                "context": {"tension": state.axp_ratio, "enriched_docs": []},
                "traces": [{"steps": [{"inputs": {"payload": reason}}]}]
            }
            delta = self.xor_engine.synth([synthetic_basis])
            if delta:
                self.signature.mutate(delta)
        
        return {
            "status": "closed",
            "frame_ref": frame.frame_id,
            "message": "흐름이 억제되었으며 Theoria 레지스트리에 닫힘이 증명됨."
        }


# ==========================================
# [신규] 구조화된 스캐너 클래스
# ==========================================
class TopologicalScanner:
    """디렉토리를 순회하며 Lineage를 추출하고 TregEdge를 통해 위상을 시뮬레이션하는 궤적 스캐너"""
    
    def __init__(self, base_root: str, target_rel_path: str):
        self.base_root = Path(base_root)
        self.target_dir = self.base_root / target_rel_path
        
        # 시스템 브릿지 초기화 (Composition)
        self.registry = FrameRegistry()
        self.xor_engine = TrajectoryXor(tension_threshold=0.5)
        self.signature = SignatureBound(
            module_id="meta.self.treg_scanner",
            base_instructions="Dynamic multi-ext path-based lineage traversal",
            input_fields=[], output_fields=[]
        )
        self.gate = TregEdge(registry=self.registry, signature=self.signature, xor_engine=self.xor_engine)

    def _extract_lineage(self, filepath: Path) -> str:
        """단일 파일에서 확장자에 맞는 Lineage 추출 또는 폴백 반환"""
        ext = filepath.suffix
        lineage_prefix = FILE_FORMATS.get(ext, FILE_FORMATS[".md"])["lineage"]

        try:
            with filepath.open('r', encoding='utf-8') as f:
                for _ in range(10):
                    line = f.readline()
                    if not line: break
                    if lineage_prefix in line:
                        return line.split(lineage_prefix)[1].strip()
        except Exception as e:
            log.warning(f"[extract_fail] {filepath}: {e}")
        
        rel_path = filepath.relative_to(self.base_root)
        return str(rel_path.with_suffix('')).replace("/", ".").replace("\\", ".")

    def scan(self) -> List[str]:
        """지정된 디렉토리를 순회하여 유효한 Lineage 목록을 반환"""
        if not self.target_dir.exists() or not self.target_dir.is_dir():
            log.error(f"[Error] 지정된 경로가 존재하지 않거나 디렉토리가 아닙니다: {self.target_dir}")
            return []

        log.info(f">>> 위상 스캔 시작: {self.target_dir}")
        extracted_lineages = []
        
        for file_path in self.target_dir.rglob("*"):
            if (
                file_path.is_file() 
                and file_path.suffix in TARGET_EXTENSIONS 
                and not file_path.name.startswith(".") 
                and not any(p in EXCLUDED_DIRS for p in file_path.parts)
            ):
                lineage = self._extract_lineage(file_path)
                extracted_lineages.append(lineage)
                
        return extracted_lineages

    def simulate(self, lineages: List[str], stress_target: str = None):
        """추출된 Lineage들을 대상으로 Traversal 시뮬레이션 실행"""
        if not lineages:
            log.info("발견된 Lineage 대상 파일이 없습니다.")
            return

        log.info(f"\n--- 총 {len(lineages)}개의 대상 Lineage 확보. 순차 Traversal 실행 ---")
        
        for lin in lineages:
            log.info(f"\n[Traverse Request] {lin}")
            
            # 스트레스 타겟이 지정되었고, 현재 lineage가 그 타겟을 포함하면 과부하 발생
            current_axp = 1.5 if stress_target and stress_target in lin else 0.5
            
            state = PhaseState(
                membrane_bound=True, 
                axp_ratio=current_axp, 
                ctla_4_expression=0.1, 
                cd28_expression=0.8, 
                lineage_path=lin
            )
            res = self.gate.traverse(state)
            log.info(f"  ↳ 결과: {res}")

        log.info("\n>>> 최종 위상 공간(Φ) 상태 스냅샷")
        log.info(self.signature.dump_state())

def main():
    parser = argparse.ArgumentParser(description="Treg Edge Lineage Scanner")
    parser.add_argument("--path", type=str, default="", help="Target directory path relative to SELF_ROOT")
    parser.add_argument("--stress", type=str, default="", help="Keyword in lineage to apply stress (AxP > 1.0) for testing")
    args = parser.parse_args()

    log.info(f">>> 시스템 브릿지 초기화 중... (Root: {SELF_ROOT})")
    
    scanner = TopologicalScanner(base_root=SELF_ROOT, target_rel_path=args.path)
    lineages = scanner.scan()
    scanner.simulate(lineages, stress_target=args.stress if args.stress else None)

if __name__ == "__main__":
    main()