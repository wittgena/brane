# bound.exam.ingester
## @lineage: debug.exam.spec.ingester
## @lineage: meta.flow.ingest.spec
import argparse
import json
import re
import yaml
from pathlib import Path
from watcher.plane.emitter import get_emitter
from phase.bind.resolver import resolve_path

log = get_emitter('ingest.spec')
SPEC_WORKSPACE = resolve_path("workspace") / "spec"
ISSUE_WORKSPACE = resolve_path("workspace") / "issue"

class SpecIngestor:
    """
    @role: Custom Spec Document Ingestor
    @desc: '@' 기반의 메타데이터와 Markdown 본문이 결합된 Spec을 JSON 위상으로 변환
    """
    def parse_spec(self, filepath: Path) -> dict:
        content = filepath.read_text(encoding='utf-8')
        
        ## 메타데이터 영역과 본문 영역을 첫 번째 '##' 기준으로 분리
        parts = re.split(r'\n(?=## )', content, maxsplit=1)
        meta_text = parts[0]
        body_text = parts[1] if len(parts) > 1 else ""

        ## 메타데이터 파싱 (@ 제거 후 YAML로 변환)
        clean_meta = re.sub(r'(?m)^@', '', meta_text)
        try:
            metadata = yaml.safe_load(clean_meta) or {}
        except Exception as e:
            log.error(f"Metadata YAML 파싱 실패: {e}")
            metadata = {}

        def get_section(title: str) -> str:
            ## "## title" 부터 다음 "## "이 나오기 전(또는 문서 끝)까지 추출
            match = re.search(fr'## {title}\n(.*?)(?=\n## |\Z)', body_text, re.DOTALL)
            return match.group(1).strip() if match else ""

        ## 재현 코드(Reproduction Code) 정제 (```rust 등 마크다운 코드블록 제거)
        raw_repro = get_section("Reproduction Code")
        code_match = re.search(r'```(?:\w+)?\n(.*?)\n```', raw_repro, re.DOTALL)
        repro_code = code_match.group(1).strip() if code_match else raw_repro

        tech_stack = metadata.get("tech_stack", "")
        if isinstance(tech_stack, list):
            tech_stack = ", ".join(tech_stack)

        issue_id = str(metadata.get("issue_number", "unknown"))
        repo = metadata.get("target_repo", "unknown/unknown")
        target_json = {
            "id": issue_id,
            "repo": repo,
            "url": metadata.get("issue_url", ""),
            "reproduction_code": repro_code,
            "expected_target_files": metadata.get("target_files", []),
            "summary": {
                "symptom": get_section("Symptom"),
                "cause": get_section("Root Cause"),
                "tech_stack": tech_stack
            },
            "control_points": get_section("Control Points"), 
            "source_spec": filepath.name
        }
        
        return target_json, issue_id, repo

    def run(self, spec_file: str):
        spec_path = Path(SPEC_WORKSPACE / spec_file)
        if not spec_path.exists():
            log.error(f"Spec 파일을 찾을 수 없습니다: {spec_path}")
            return

        log.info(f"[*] Ingesting Spec Document: {spec_path.name}")
        
        target_json, issue_id, repo = self.parse_spec(spec_path)
        repo_filename = repo.replace('/', '-')
        out_filename = f"{repo_filename}-issues-{issue_id}.json"
        out_filepath = ISSUE_WORKSPACE / out_filename
        
        with open(out_filepath, "w", encoding="utf-8") as f:
            json.dump(target_json, f, ensure_ascii=False, indent=4)
            
        log.info("=" * 59)
        log.info(f"Spec: {out_filename}")
        log.info(f"  - Target ID:    {issue_id}")
        log.info(f"  - Repository:   {repo}")
        log.info(f"  - Target Files: {len(target_json['expected_target_files'])} files detected")
        log.info(f"  - Symptom:      {target_json['summary']['symptom'][:50]}...")
        log.info("=" * 59)

def main():
    parser = argparse.ArgumentParser(description="Spec Ingestor")
    parser.add_argument("--file", type=str, required=True, help="Path to the custom Markdown Spec file")
    args = parser.parse_args()

    ingestor = SpecIngestor()
    ingestor.run(args.file)

if __name__ == "__main__":
    main()