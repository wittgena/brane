# anchor.exam.metadata
## @lineage: bound.exam.metadata
## @lineage: debug.exam.metadata
## @lineage: debugger.flow.metadata
import sys
import argparse
import asyncio
import json
from pathlib import Path
from typing import List, Optional, Dict, Any
from frame.scope.workflow.router import Workflow, step, Event, StartEvent, StopEvent, router_rules, ErrorEvent
from arch.xor.store import ResidueStore, ResidueSnapshot
from meta.xor.adapter.exam.example import Example
from watcher.kernel.xphi.flow.xearch import Xor
from watcher.plane.emitter import get_logger
from phase.bind.resolver import resolve_path

log = get_logger("xor.metadata")

try:
    METADATA_ROOT = resolve_path("io") / "metadata"
    MANIFEST_FILE = METADATA_ROOT / "manifest.json"
except Exception as e:
    log.error(f"[error] 경로 설정 실패: {e}")
    sys.exit(1)

class NativeResidueRetriever:
    """RocksDB(ResidueStore)에 쌓인 위상 잔여물(Snapshot)을 검색하는 네이티브 검색기"""
    def __init__(self, persist_dir: str):
        # LlamaIndex의 StorageContext 초기화를 대체
        self.store = ResidueStore(path=persist_dir)
        log.info(f"[NativeIndex] ResidueStore (RocksDB) 연결 완료: {persist_dir}")

    async def retrieve(self, query: str, filters: dict = None) -> List[Example]:
        """검색을 수행하고 결과를 DSPy 표준 규격인 Example 리스트로 반환"""
        prefix = filters.get("block_type", "") if filters else ""
        snapshot: Optional[ResidueSnapshot] = await asyncio.to_thread(self.store.retrieve_latest, prefix)
        
        examples = []
        if snapshot:
            for block in snapshot.blocks:
                ex = Example(
                    score=0.99,  # TODO: BM25/Vector 유사도 점수 산출 로직 연동
                    block_type=block.get("section", "unknown"),
                    file_path=block.get("file_path", "unknown"),
                    section_path=block.get("section_path", "unknown"),
                    raw_text=block.get("content", "")
                )
                examples.append(ex)
        return examples

class XorSearchEvent(Event):
    query: str
    block_type: Optional[str] = None
    status: str = "success"

class LocalSearchEvent(Event):
    query: str
    block_type: Optional[str] = None
    persist_dir: str = ""
    status: str = "success"


@router_rules
class XorSearch(Workflow):
    class Meta:
        trans_rules = {"error": ErrorEvent}
        flow = ["route_query", ["xor", "search_local"]]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.xor_client = Xor()
        self.local_retriever = None  # NativeResidueRetriever 인스턴스 보관

    def _load_manifest(self) -> Optional[Dict[str, Any]]:
        if not MANIFEST_FILE.exists():
            log.warning(f"[Manifest] 상태 파일을 찾을 수 없습니다: {MANIFEST_FILE}")
            return None
        try:
            with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log.error(f"[Manifest] 파일 읽기 실패: {e}")
            return None

    @step
    async def route_query(self, ev: StartEvent) -> XorSearchEvent | LocalSearchEvent | ErrorEvent:
        query = getattr(ev, "query", None)
        engine = getattr(ev, "engine", "xor")
        block_type = getattr(ev, "block_type", None)

        if not query:
            return ErrorEvent(msg="검색어(query)가 필요합니다.")

        if engine.lower() in ["llama", "local"]:
            manifest = self._load_manifest()
            if not manifest:
                log.warning("로컬 메타데이터가 없어 XOR로 Fallback 합니다.")
                return XorSearchEvent(query=query, block_type=block_type)
            
            return LocalSearchEvent(
                query=query, 
                block_type=block_type, 
                persist_dir=manifest.get("persist_dir", str(METADATA_ROOT))
            )
        
        return XorSearchEvent(query=query, block_type=block_type)

    @step
    async def xor(self, ev: XorSearchEvent) -> StopEvent:
        log.info("[Search:Xor] 원격 서버 쿼리 중...")
        try:
            raw_results = await asyncio.to_thread(self.xor_client.search, ev.query, ev.block_type)
        except Exception as e:
            return XorSearchEvent(query=ev.query, block_type=ev.block_type, status="error", msg=f"XOR 서버 통신 실패: {e}")
        
        results = [
            {
                "engine": "XOR",
                "score": getattr(r, "score", 0.0),
                "block_type": getattr(r, "block_type", "unknown"),
                "file_path": getattr(r, "file_path", "unknown"),
                "section_path": getattr(r, "section_path", "unknown")
            }
            for r in raw_results
        ]
        return StopEvent(result=results)

    @step
    async def search_local(self, ev: LocalSearchEvent) -> StopEvent | XorSearchEvent:
        log.info(f"[Search:Local] ResidueStore 스캔 중: {ev.persist_dir}")
        
        if self.local_retriever is None:
            try:
                self.local_retriever = NativeResidueRetriever(persist_dir=ev.persist_dir)
            except Exception as e:
                log.error(f"[Search:Local] ResidueStore 로드 실패 ({e}). XOR 우회합니다.")
                return XorSearchEvent(query=ev.query, block_type=ev.block_type)

        filters = {"block_type": ev.block_type} if ev.block_type else None
        
        # LlamaIndex 검색을 수행하던 로직이 Native Retriever + DSPy Example 호출로 완전 변경됨
        examples: List[Example] = await self.local_retriever.retrieve(ev.query, filters=filters)
        
        results = [
            {
                "engine": "LOCAL_RESIDUE",
                "score": ex.score,
                "block_type": ex.get("block_type", "unknown"),
                "file_path": ex.get("file_path", "unknown"),
                "section_path": ex.get("section_path", "unknown")
            }
            for ex in examples
        ]
        return StopEvent(result=results)

    @step
    async def handle_error(self, ev: ErrorEvent) -> StopEvent:
        log.error(f"[Workflow:Halt] 검색 프로세스 중단: {ev.msg}")
        return StopEvent(result=[])


async def main():
    parser = argparse.ArgumentParser(description="Metadata-aware Dual Search")
    parser.add_argument("query", nargs="*", help="검색어")
    parser.add_argument("--engine", choices=["xor", "llama", "local"], default="xor")
    parser.add_argument("--type", dest="block_type")
    args = parser.parse_args()

    query_str = " ".join(args.query) if args.query else ""
    workflow = XorSearch(timeout=30.0)
    
    try:
        results = await workflow.run(query=query_str, engine=args.engine, block_type=args.block_type)
        if not results:
            log.info("\n[Result] 검색 결과가 없거나 시스템 오류로 중단되었습니다.")
            return
            
        log.info(f"\n[Final Results] {len(results)} matches found\n")
        for r in results:
            log.info(f"{r['score']:.3f} | {r['block_type']} | {r['section_path']} | {r['file_path']}")
            
    except Exception as e:
        log.error(f"실행 중 치명적 오류: {e}")

if __name__ == "__main__":
    asyncio.run(main())