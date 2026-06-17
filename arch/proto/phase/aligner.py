# arch.proto.phase.aligner
import abc
from pathlib import Path
from typing import List, Dict, Any, Tuple, Callable
from collections import defaultdict
from watcher.plane.emitter import get_emitter, flow_scope

## alignment 과정에서 다루는 최소 단위 상태
AlignRecord = Dict[str, Any]

## @group_by: Axis projection
def group_by(
    records: List[AlignRecord],
    key_fn: Callable[[AlignRecord], str],
) -> List[Dict[str, Any]]:
    ## aligner가 공유하는 공통 그룹화 원형
    clusters = defaultdict(list)
    for r in records:
        clusters[key_fn(r)].append(r)

    return [
        {"path": k, "items": v}
        for k, v in sorted(clusters.items())
    ]

## Base Template
class PhaseAligner(abc.ABC):
    """
    Alignment pipeline의 공통 구조.
    - ψ: drift 관측 상태
    - ∂Φ: anchor 기준으로 정렬된 상태
    - Φ′: axis 기준으로 grouping된 topology
    - Φ: 외부로 표현된 closure
    """
    def __init__(self, root_dir: str, emitter_name: str = "phase.aligner"):
        self.root_dir = root_dir
        self.emitter = get_emitter(emitter_name, boundary=root_dir)

    @abc.abstractmethod
    def scan(self, **kwargs) -> Tuple[List[AlignRecord], int, int]:
        """
        ## Drift detection stage.
        :return: (mismatches_list, matched_count, mismatched_count)
        """
        pass

    def align(self, mismatches: List[AlignRecord], **kwargs) -> List[AlignRecord]:
        apply_changes = kwargs.get("apply", False)
        results = []

        with flow_scope(phase="ALIGN", mode="apply" if apply_changes else "dry_run"):
            for record in mismatches:
                path_str = record["path"]
                modified_code = record["modified"]
                
                if apply_changes:
                    try:
                        Path(path_str).write_text(modified_code, encoding="utf-8")
                        record["status"] = "applied"
                        self.emitter.crit(f"Updated: {path_str}") 
                    except Exception as e:
                        record["status"] = f"failed: {e}"
                        self.emitter.error(f"Failed to write {path_str}: {e}")
                else:
                    record["status"] = "dry_run"
                    self.emitter.info(f"Dry-run, would update: {path_str}")
                
                results.append(record)

        return results

    def analyze(
        self, 
        records: List[AlignRecord], 
        axis: str, 
        group_keys: Dict[str, Callable[[AlignRecord], str]]
    ) -> List[Dict[str, Any]]:
        ## Axis projection stage: 정렬된 상태를 특정 axis로 투영하여 의미 있는 군집 구조를 형성
        ## 기본 전략 설정 (없으면 첫 번째 전략을 사용)
        fallback_key = list(group_keys.values())[0] if group_keys else lambda x: "unknown"
        key_fn = group_keys.get(axis, fallback_key)
        return group_by(records, key_fn)

    def emit(self, clusters: List[Dict[str, Any]], matched: int, mismatched: int, axis: str ) -> Dict[str, Any]: 
        ## Closure stage: alignment 결과를 외부 시스템이 사용할 수 있는 형태로 반환
        return { 
            "summary": { 
                "root_dir": str(self.root_dir), 
                "total_files": matched + mismatched,
                "matched": matched,
                "mismatched": mismatched,
                "grouped_by": axis,
            }, 
            "clusters": clusters,
        }

    def run(self, axis: str, group_keys: Dict[str, Callable[[AlignRecord], str]], scan_kwargs: dict = None, fix_kwargs: dict = None) -> Dict[str, Any]:
        """
        Scan -> align -> Analyze -> Emit 순으로 실행 흐름을 align
        """
        scan_kwargs = scan_kwargs or {}
        fix_kwargs = fix_kwargs or {}

        ## stage.1: Scan (drift observation)
        mismatches, matched, mismatched = self.scan(**scan_kwargs)
        
        ## stage.2: align 
        results = self.align(mismatches, **fix_kwargs) if mismatches else []
        
        ## stage.3: Analyze (axis projection)
        clusters = self.analyze(results, axis, group_keys)
        
        ## stage.4: Emit (closure)
        return self.emit(clusters, matched, mismatched, axis)