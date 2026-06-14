# bound.xor.block.aggregator
## @lineage: arch.topos.bind.block.aggregator
## @lineage: meta.xor.manifold.block.aggregator
## @lineage: meta.xor.adapter.manifold.block.aggregator
## @lineage: meta.ops.trainer.block.aggregator
## @lineage: xor.block.aggregator
## @lineage: xor.residue.block.aggregator
import sys
import json
import argparse
from pathlib import Path

from bound.xor.block.emitter import main as emitter_main

from phase.bind.resolver import resolve_path
from watcher.plane.emitter import get_emitter

log = get_emitter("block.aggregator")
BLOCKS_ROOT = resolve_path("xor") / "blocks"

def aggregate_and_print_blocks(target_dir: Path):
    json_files = list(target_dir.rglob("*.json"))
    if not json_files:
        log.info(f"[info] '{target_dir}' 경로에 블록 데이터가 없습니다. 신규 생성을 시작합니다.")
        try:
            emitter_main()
        except SystemExit as e:
            if e.code != 0:
                log.error("[error] 블록 신규 생성 중 오류가 발생하여 종료합니다.")
                sys.exit(e.code)
        
        json_files = list(target_dir.rglob("*.json"))
        if not json_files:
            log.warning("[warning] 블록 생성이 실행되었으나 해당 경로에 JSON 파일이 없습니다.")
            return

    combined_blocks = []
    for filepath in json_files:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                blocks = json.load(f)
                
                for block in blocks:
                    block.pop("content", None)
                    block.pop("block_id", None)
                    block.pop("file_path", None)
                    combined_blocks.append(block)
        except Exception as e:
            log.error(f"[error] 파일 읽기 실패 ({filepath}): {e}")

    for block in combined_blocks:
        print(json.dumps(block, ensure_ascii=False))

def main():
    parser = argparse.ArgumentParser(description="Extract and aggregate blocks to JSONL")
    parser.add_argument(
        "--path", 
        type=str, 
        default="", 
        help="BLOCKS_ROOT 기준 상대 경로 (예: target/action)"
    )
    
    args, unknown = parser.parse_known_args()
    target_dir = BLOCKS_ROOT / args.path
    if not target_dir.exists():
        log.warning(f"[warning] 타겟 경로가 존재하지 않습니다: {target_dir}")
    aggregate_and_print_blocks(target_dir)

if __name__ == "__main__":
    main()