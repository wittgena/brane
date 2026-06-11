# anchor.exam.index
## @lineage: bound.exam.index
## @lineage: debug.exam.index
## @lineage: debugger.flow.index
import sys
import json
import asyncio
import time
from pathlib import Path
from typing import Dict, List, Any
from frame.scope.workflow.router import (
    Workflow, step, Event, StartEvent, StopEvent, router_rules, ErrorEvent
)
from watcher.plane.emitter import get_logger
from watcher.kernel.xphi.flow.xearch import Xor 
from watcher.kernel.xphi.flow.ktory import EmissionRunner, KotlinPSITool, RipgrepTool
from phase.bind.resolver import find_current_self, resolve_path
from phase.bind.folding import folding
from arch.xor.block.extractor import extract_block_from_file, Block

log = get_logger("workflow.index")

try:
    SELF_ROOT = find_current_self()
    XOR_ROOT = resolve_path("xor")
    METADATA_ROOT = resolve_path("io") / "metadata"
    BLOCKS_ROOT = XOR_ROOT / "blocks"
except Exception as e:
    log.error(f"[error] 기준면(.self)을 찾을 수 없음: {e}")
    sys.exit(1)

class RepoAnalyzedEvent(Event):
    target_files: List[Path]
    kt_contracts_map: Dict[str, list]
    status: str = "success"

class ExtractionDoneEvent(Event):
    """추출이 완료되어 Xor 인덱싱 준비가 끝남을 알리는 이벤트"""
    json_path: Path
    total_blocks: int
    status: str = "success"


@router_rules
class SelfIndexingWorkflow(Workflow):
    """
    ### @project.regime("indexing")
    @flow: analyze -> prepare -> build
    @desc: Surgent가 자신의 레포지토리(Self)를 ktory로 파싱하고 xearch로 인덱싱하는 자기-인지 루프.
    """
    class Meta:
        trans_rules = {"error": ErrorEvent}
        flow = ["analyze_repository", "extract_and_prepare", "trigger_xor_indexing"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.xor_client = Xor()

    @step
    async def analyze_repository(self, ev: StartEvent) -> RepoAnalyzedEvent | ErrorEvent:
        """Step 1: 대상 파일 목록 및 정적 분석 (AST 추출)"""
        target_dir = getattr(ev, "target_dir", None)
        if not target_dir:
            return ErrorEvent(msg="target_dir가 StartEvent에 필요합니다.")

        root = Path(target_dir)
        log.info(f"[Step 1] '{root.name}' 자체 프로젝트 분석 시작...")

        kt_runner = EmissionRunner([KotlinPSITool(), RipgrepTool()])
        all_kt_contracts = await asyncio.to_thread(kt_runner.run, str(root))
        
        kt_contracts_map = {}
        for fact in all_kt_contracts:
            if fact.source:
                abs_file_path = str(Path(fact.source).absolute())
                kt_contracts_map.setdefault(abs_file_path, []).append(fact)

        target_files = list(root.rglob("*.md")) + list(root.rglob("*.py")) + list(root.rglob("*.kt"))
        log.info(f"[Step 1] AST 분석 완료. 인덱싱 대상 파일: {len(target_files)}개")
        
        return RepoAnalyzedEvent(target_files=target_files, kt_contracts_map=kt_contracts_map)

    @step
    async def extract_and_prepare(self, ev: RepoAnalyzedEvent) -> ExtractionDoneEvent | ErrorEvent:
        """Step 2: 파일을 파싱하여 Xor가 소비할 JSON 형태로 직렬화합니다."""
        total_blocks = 0
        
        def _process_files():
            nonlocal total_blocks
            for path in ev.target_files:
                try:
                    blocks = extract_block_from_file(path, ev.kt_contracts_map)
                    if not blocks:
                        continue
                    
                    total_blocks += len(blocks)
                    blocks_dict = [b.to_dict() for b in blocks]
                    
                    try:
                        rel_path = path.relative_to(SELF_ROOT)
                    except ValueError:
                        rel_path = path.name

                    out_path = BLOCKS_ROOT / Path(rel_path).with_suffix(".json")
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_text(json.dumps(blocks_dict, indent=2, ensure_ascii=False), encoding="utf-8")
                
                except Exception as e:
                    log.error(f"[error] {path} 파싱 실패: {e}")

        await asyncio.to_thread(_process_files)
        log.info(f"[Step 2] 위상 데이터 추출 완료. 총 {total_blocks}개 블록 직렬화됨.")
        
        return ExtractionDoneEvent(json_path=BLOCKS_ROOT, total_blocks=total_blocks)

    @step
    async def trigger_xor_indexing(self, ev: ExtractionDoneEvent) -> StopEvent:
        """Step 3: 추출된 JSON을 기반으로 Xor 엔진에 인덱싱을 요청하고 메타데이터를 갱신합니다."""
        target_path = str(ev.json_path)
        log.info(f"[Step 3] Xor 네이티브 인덱싱 트리거: {target_path}")
        
        def _index_and_manifest():
            # 1. Xor 인덱싱 호출
            self.xor_client.index_dist(target_path)

            # 2. 단일 통합 메타데이터(Manifest) 구성 (xor.metadata가 참조할 파일)
            METADATA_ROOT.mkdir(parents=True, exist_ok=True)
            metadata = {
                "engine": "xor-ktory-native",
                "indexed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "persist_dir": target_path,
                "total_nodes": ev.total_blocks,
                "mode": "self-referential"
            }
            
            metadata_file = METADATA_ROOT / "manifest.json"
            with open(metadata_file, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
                
            return metadata_file.name

        try:
            manifest_name = await asyncio.to_thread(_index_and_manifest)
            return StopEvent(result={
                "status": "success",
                "message": f"자체 인덱싱 완료 (Manifest: {manifest_name})",
                "total_blocks": ev.total_blocks
            })
        except Exception as e:
            return StopEvent(result={"status": "error", "message": f"Xor 인덱싱 실패: {e}"})

    @step
    async def handle_error(self, ev: ErrorEvent) -> StopEvent:
        log.error(f"[Workflow:Halt] 파이프라인 중단: {getattr(ev, 'msg', 'Unknown')}")
        return StopEvent(result={"status": "error", "message": getattr(ev, 'msg', 'Unknown')})


async def run_pipeline(repo_name: str):
    """위상적 보호막(Membrane) 내에서 워크플로우를 실행"""
    root = SELF_ROOT / Path(repo_name)
    if not root.exists():
        log.error(f"Directory not found: {root}")
        sys.exit(1)

    # DualIngestionWorkflow -> SelfIndexingWorkflow 이름 변경
    workflow = SelfIndexingWorkflow(timeout=600.0)

    # 지능형 접합 (Smart Bounding)
    with folding(workflow, workflow.xor_client, re_entry_limit=3) as (b_workflow, b_xor):
        log.info(f"[System] 위상 전사 완료. '{repo_name}' 자기 인지 파이프라인 가동.")
        
        # StartEvent의 속성 주입 규격에 맞춤
        result = await b_workflow.run(target_dir=str(root))
    
    # 결과 출력
    print("\n" + "="*40)
    print("[Self-Indexing Result Summary]")
    print(f"- Status : {result.get('status')}")
    print(f"- Blocks : {result.get('total_blocks')} Nodes")
    print(f"- Msg    : {result.get('message')}")
    print("="*40)

def main():
    parser = argparse.ArgumentParser(description="Self-Referential Indexing Pipeline")
    parser.add_argument("--repo", required=True, help="분석할 레포지토리 이름 (Surgent/Theoria)")
    args = parser.parse_args()
    
    try:
        asyncio.run(run_pipeline(args.repo))
    except Exception as e:
        log.critical(f"[System Failure] 위상 붕괴: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()