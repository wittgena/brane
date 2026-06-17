# phase.ator.reflect.workspace
## @lineage: phase.activator.reflect.workspace
import os
from pathlib import Path
from arch.contract.registry.unified import contract
from watcher.plane.emitter import get_emitter

log = get_emitter('reflect.workspace')

@contract.cli(
    name="materialize_workspace",
    args=["--init-dirs"],
    # [Point] 해당 태그를 부여하여 Activator가 두 번째 순서로 자동 실행하게 만듦
    tags=["bootstrap", "core_materialized"] 
)
def main():
    log.info("[Core] Materializing physical boundaries...")
    
    ## 필수 디렉토리 실체화
    required_dirs = ["xor/bound", "xor/cache", "anchor/io"]
    for d in required_dirs:
        Path(d).mkdir(parents=True, exist_ok=True)
        log.info(f"  └── Created directory: {d}")

    ## 센서가 잡아준 외부 경로를 로컬에 바인딩 (Symlink)
    cloud_io = Path(os.path.expanduser("~/Dropbox"))
    local_io = Path("anchor/io")
    if cloud_io.exists() and not local_io.exists():
        os.symlink(cloud_io, local_io)
        log.info(f"  └── Symlink materialized: {local_io} -> {cloud_io}")

    status = {"status": "success", "phase": "core_materialized"}
    print(status)

if __name__ == "__main__":
    main()