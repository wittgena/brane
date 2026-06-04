# hub.sphere.validator.module
## @lineage: sphere.validator.module
## @lineage: debugger.sphere.validator.module
## @lineage: debug.sphere.validator.module
## @lineage: bound.sphere.validator.module
## @lineage: gov.sphere.validator.module
## @lineage: iso.sphere.validator.module
## @lineage: iso.validator.module
"""
@desc: 최종 위상(Topology) 및 PromQL 의존성 불변성 검증
@phase: invariants_verified (Bootstrap Phase 6)
"""
import sys
import yaml
import re
import argparse
from pathlib import Path
from typing import Dict, Tuple, List, Any
from watcher.plane.emitter import get_emitter
from arch.contract.registry.unified import cli_contract
from arch.xor.block.parser.md import MdAstParser
from arch.xor.block.extractor import BlockExtractor
from hub.sphere.validator.promql import MarkdownConfigExtractor, PromQLValidator, LoopTopologyValidator

log = get_emitter("validator.module")

class SystemInvariantsValidator:
    """
    @role: 최종 정합성 검증 오케스트레이터
    """
    def __init__(self):
        self.parser_cls = MdAstParser
        self.extractor = BlockExtractor()

    def run_validation(self, target_repo: str) -> bool:
        """지정된 디렉토리 내의 설계 문서(.md)들을 스캔하여 정합성 검증"""
        target_path = Path(target_repo)
        md_files = list(target_path.rglob("*.md"))
        
        if not md_files:
            log.warning(f"[Φ:skip] No markdown files found in {target_repo}")
            return True

        all_valid = True
        for md_file in md_files:
            log.info(f"\n[Ψ:validate] Checking invariant surface: {md_file.name}")
            
            # 1. 파싱 및 추출
            doc = self.parser_cls(md_file).parse()
            blocks = self.extractor.extract(doc).to_dict()
            configs = MarkdownConfigExtractor.extract(blocks)

            if not configs:
                continue

            # 2. 커널 검증 (PromQL 의존성 등)
            rule_path = next((k for k in configs.keys() if "rules" in k), None)
            if rule_path:
                errors, _, _ = PromQLValidator.validate(configs[rule_path])
                if errors:
                    for err in errors:
                        log.error(f"  [∂Φ:error] {err}")
                    all_valid = False

            # 3. 위상 폐쇄(Loop Closure) 검증
            topology = LoopTopologyValidator.validate(configs)
            if not topology.get("loop_closure (Ψ -> Φ -> Ψ')", False):
                log.error(f"  [Ψ:broken] Loop closure failed in {md_file.name}")
                all_valid = False
            else:
                log.info(f"  [Ψ:stable] Invariant loop verified.")

        return all_valid

@cli_contract(
    name="invariants_verified",
    args=["--repo", "meta"],
    tags=["bootstrap", "invariants_verified"] # 부트스트랩 최종 단계 태그
)
def main():
    parser = argparse.ArgumentParser(description="System Invariants Validator")
    parser.add_argument("--repo", type=str, default=".", help="Target directory for .md files")
    args, _ = parser.parse_known_args()

    validator = SystemInvariantsValidator()
    success = validator.run_validation(args.repo)
    if not success:
        log.error("[fatal] System invariant verification failed.")
        sys.exit(1)
    
    log.info("\n[Φ:threshold] All invariants verified. System ready.")

if __name__ == "__main__":
    main()