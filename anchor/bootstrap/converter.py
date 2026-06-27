# anchor.bootstrap.converter
## @lineage: anchor.switch.bootstrap.converter
import os
import sys
import argparse
import threading
import subprocess
from pathlib import Path
from typing import List, Dict

from phase.bind.resolver import find_current_self
from arch.contract.registry.unified import contract, registry
from phase.runtime.cli.executor import CliTaskAdapter, parse_local, dispatch_cli
from watcher.plane.emitter import get_emitter

log = get_emitter("bootstrap.converter", phase="SYSTEM")

try:
    SELF_ROOT = find_current_self()
except Exception as e:
    log.error(f"[error] Cannot find base plane (.self): {e}")
    sys.exit(1)

class BootstrapConverter:
    def __init__(self, target_repo: str, dry_run: bool = False):
        self.target_repo = target_repo
        self.dest_dir = SELF_ROOT / self.target_repo
        self.dry_run = dry_run

        self.import_routing_table: List[Dict[str, str]] = [
            {"old": "litellm.types.llms.openai", "new": "anchor.switch.params"},
            {"old": "litellm.types.responses.main", "new": "anchor.switch.params"},
            {"old": "litellm.types.completion", "new": "anchor.switch.params"},
            {"old": "litellm.types.rerank", "new": "anchor.switch.params"},
            {"old": "litellm.types.utils", "new": "anchor.switch.params"},
            {"old": "litellm.utils", "new": "anchor.switch.params"},
            {"old": "litellm", "new": "anchor.switch.params"} # Catch-all fallback
        ]

    def _execute_isolated_subtask_sync(self, command_name: str, args: list):
        """격리된 OS 서브프로세스 실행 및 실시간 로그 파이프 연결"""
        task_info_list = registry.registered_cli_tasks.get(command_name)
        if not task_info_list:
            raise RuntimeError(f"Cannot find contract '{command_name}' in registry.")

        module_fqn = task_info_list[0].get("module_fqn")
        cmd = [sys.executable, "-m", module_fqn] + args
        log.info(f"  -> Spawning Subprocess: {' '.join(cmd)}")
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(SELF_ROOT),
            text=True,
            bufsize=1
        )

        def stream_reader(stream, prefix=""):
            for line in stream:
                text = line.strip()
                if text:
                    log.info(f"  {prefix}| {text}")

        t_out = threading.Thread(target=stream_reader, args=(process.stdout, ""))
        t_err = threading.Thread(target=stream_reader, args=(process.stderr, "[ERR]"))
        t_out.start()
        t_err.start()

        t_out.join()
        t_err.join()
        process.wait()
        
        if process.returncode != 0:
            raise RuntimeError(f"Sub-task '{command_name}' failed with return code {process.returncode}")
        
        return True

    def phase_1_align_imports(self):
        """AST Import 경로 치환"""
        log.info(f"\n## @mutate [Phase 1]: Aligning imports for '{self.target_repo}'")
        
        for route in self.import_routing_table:
            old_prefix = route["old"]
            new_prefix = route["new"]
            
            log.signal(f"[TASK] Routing: {old_prefix} ➔ {new_prefix}")
            
            args = [
                "--local", 
                "--repo", self.target_repo,
                "--old", old_prefix, 
                "--new", new_prefix
            ]
            if self.dry_run:
                args.append("--dry-run")

            self._execute_isolated_subtask_sync("align.imports", args)

    def phase_2_inject_config_proxy(self):
        """전역 상태 객체(config) AST 프록시 주입"""
        log.info(f"\n## @mutate [Phase 2]: Injecting Config Resolver Proxy for '{self.target_repo}'")
        
        ## @ex: self._execute_isolated_subtask_sync("align.config_proxy", args)
        log.info("  -> (Reserved for dynamic state AST transformation: litellm.xxx ➔ config.xxx)")

    def run(self):
        """단일 실행 파이프라인"""
        if not self.dest_dir.is_dir():
            log.error(f"[ERROR] Target repository '{self.target_repo}' does not exist at {self.dest_dir}")
            sys.exit(1)
            
        mode = "DRY-RUN" if self.dry_run else "APPLY (DESTRUCTIVE)"
        log.info(f"=== Starting Switch Conversion [{mode}] ===")

        try:
            self.phase_1_align_imports()
            self.phase_2_inject_config_proxy()
            log.info(f"\n[SUCCESS] All switch mutations completed for '{self.target_repo}'.")
        except Exception as e:
            log.error(f"\n[CRITICAL ERROR] Pipeline halted during execution: {e}")
            raise


def entry_task(args):
    parser = argparse.ArgumentParser(description="Brane Litellm-to-Switch Refactoring Orchestrator")
    parser.add_argument("--repo", required=True, help="Target repository folder name (e.g., openhands)")
    parser.add_argument("--dry-run", action="store_true", help="Simulate AST mutation without writing to disk")
    parsed_args = parser.parse_args(args)
    
    runner = BootstrapConverter(
        target_repo=parsed_args.repo, 
        dry_run=parsed_args.dry_run
    )
    return CliTaskAdapter(runner.run)


@contract.cli(
    name="bootstrap.converter", 
    args=["--repo", "--dry-run"],
    tags=["switch", "mutation", "refactor"],
    entry="entry_task" 
)
def main(args=None):
    if args is not None:
        return entry_task(args)
    bound_args, remain = parse_local(sys.argv[1:])
    if bound_args.local:
        entry_task(remain).run()
    else:
        dispatch_cli("bootstrap.converter", entry_task, __file__)

if __name__ == "__main__":
    main()