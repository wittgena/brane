# bound.xor.block.emitter
## @lineage: arch.xor.block.emitter
import re
import sys
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Union, Dict

from anchor.xphi.flow.ktory import EmissionRunner, KotlinPSITool, RipgrepTool

from arch.xor.block.extractor import extract_block_from_file, Block
from phase.bind.resolver import find_current_self, resolve_path
from watcher.plane.emitter import get_logger

log = get_logger("block.emitter")

try:
    SELF_ROOT = find_current_self()
    BLOCKS_ROOT = resolve_path("xor") / "blocks"
    BLOCKS_ROOT.mkdir(parents=True, exist_ok=True)
except Exception as e:
    log.error(f"[error] 기준면(.self)을 찾을 수 없음: {e}")
    sys.exit(1)

def iter_supported_files(root: Path):
    for ext in ("*.md", "*.py", "*.kt"):
        yield from root.rglob(ext)

def save_blocks_json(blocks: List[dict], source_path: Path):
    try:
        rel_path = source_path.relative_to(SELF_ROOT)
    except ValueError:
        rel_path = source_path.name

    out_path = BLOCKS_ROOT / Path(rel_path).with_suffix(".json")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    out_path.write_text(
        json.dumps(blocks, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    log.info(f"[json written] {out_path}")

def process_file(path: Path, kt_contracts: dict = None):
    """단독 실행 시 파일을 파싱하고, 결과를 출력 및 저장합니다."""
    blocks = extract_block_from_file(path, kt_contracts)
    
    if not blocks:
        return

    print(f"\n[BLOCK COUNT] {len(blocks)} :: {path}")
    for b in blocks:
        print(f"{b.order_index:03d} | {b.block_type} | {b.section_path}")
    
    save_blocks_json(blocks, path)

def main():
    args = sys.argv[1:]
    if not args:
        print("Usage:")
        print("  python -m manifold.block.parser --repo <root>")
        sys.exit(1)

    if "--repo" in args:
        idx = args.index("--repo")
        if idx + 1 >= len(args):
            print("Error: --repo requires a repo name")
            sys.exit(1)

        root = SELF_ROOT / Path(args[idx + 1])
        if not root.exists():
            print(f"Directory not found: {root}")
            sys.exit(1)

        log.info("[ktory] Kotlin 프로젝트 일괄 분석 시작...")
        kt_runner = EmissionRunner([
            KotlinPSITool(), 
            RipgrepTool()
        ])

        all_kt_contracts = kt_runner.run(str(root))
        kt_contracts_map = {}
        for fact in all_kt_contracts:
            if fact.source:
                abs_file_path = str(Path(fact.source).absolute())
                kt_contracts_map.setdefault(abs_file_path, []).append(fact)
    
        for filepath in iter_supported_files(root):
            try:
                process_file(filepath, kt_contracts_map)
            except Exception as e:
                log.error(f"[error] {filepath}: {e}")

    else:
        path = Path(args[0])
        if not path.exists():
            print(f"File not found: {path}")
            sys.exit(1)
        process_file(path)

if __name__ == "__main__":
    main()