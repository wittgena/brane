# anchor.rule.llama.mutation
import os
import sys
import shutil
import tempfile
import argparse
import json
import threading
import subprocess
import urllib.request
from urllib.error import URLError, HTTPError
from pathlib import Path
from phase.bind.resolver import find_current_self
from arch.contract.registry.unified import contract, registry
from phase.runtime.cli.executor import CliTaskAdapter, parse_local, dispatch_cli
from watcher.plane.emitter import get_emitter

log = get_emitter("llama.mutation", phase="SYSTEM")

try:
    SELF_ROOT = find_current_self()
except Exception as e:
    log.error(f"[error] Cannot find base plane (.self): {e}")
    sys.exit(1)

GITHUB_API_BASE = "https://api.github.com/repos/run-llama/llama_index/contents"
GITHUB_REPO_URL = "https://github.com/run-llama/llama_index.git"

TARGET_REPO = "brane"
ADAPTER_PATH = "anchor.adapter"
BRIDGE_DEST_PATH = "channel.bridge"

class MutationRunner:
    """GitHub API extractor and pure synchronous isolated OS process orchestrator"""
    
    def __init__(self, category: str, name: str):
        self.category = category
        self.name = name
        
        ## Separate hyphen (-) and underscore (_) naming rules - GitHub project folder names use '-', while Python package paths use '_'
        category_dir = category.replace("_", "-")
        name_dir = name.replace("_", "-")
        category_pkg = category.replace("-", "_")
        name_pkg = name.replace("-", "_")
        
        ## Combine the synthesized source path
        self.target_subpath = (
            f"llama-index-integrations/{category_pkg}/"
            f"llama-index-{category_dir}-{name_dir}/"
            f"llama_index/{category_pkg}/{name_pkg}"
        )

        ## Convert "." to "/" in NEW_PATH to construct dest_dir
        new_path_parts = BRIDGE_DEST_PATH.split(".")
        self.dest_dir = SELF_ROOT / TARGET_REPO / Path(*new_path_parts) / category_pkg / name_pkg

    def run_command_sync(self, cmd: list, cwd=None, check=True):
        log.signal(f"[RUN] {' '.join(cmd)}")
        result = subprocess.run(cmd, cwd=cwd, check=check, text=True, capture_output=True)
        if result.stdout:
            for line in result.stdout.strip().split("\n"):
                log.info(f"  | {line}")
        return result

    def _download_via_api(self, api_url: str, current_dest: Path) -> int:
        req = urllib.request.Request(api_url, headers={'User-Agent': 'Theoria-Mutation-Agent'})
        with urllib.request.urlopen(req) as response:
            items = json.loads(response.read().decode())

        if not isinstance(items, list):
            items = [items] 

        download_count = 0
        for item in items:
            if item["type"] == "file":
                if item["name"] in ["__init__.py", "README.md"]:
                    continue
                
                dest_file = current_dest / item["name"]
                log.info(f"  -> Downloading: {item['name']}")
                
                dl_req = urllib.request.Request(item["download_url"], headers={'User-Agent': 'Theoria-Mutation-Agent'})
                with urllib.request.urlopen(dl_req) as dl_resp, open(dest_file, 'wb') as f:
                    f.write(dl_resp.read())
                download_count += 1
                
            elif item["type"] == "dir":
                new_dest = current_dest / item["name"]
                new_dest.mkdir(parents=True, exist_ok=True)
                download_count += self._download_via_api(item["url"], new_dest)
                
        return download_count

    def fetch(self):
        log.info(f"## @extract: '{self.category}/{self.name}'")
        log.info(f"[*] Synthesized source path: {self.target_subpath}")
        
        self.dest_dir.mkdir(parents=True, exist_ok=True)
        api_target_url = f"{GITHUB_API_BASE}/{self.target_subpath}"

        try:
            log.info("[*] Attempting file-level extraction via GitHub API...")
            count = self._download_via_api(api_target_url, self.dest_dir)
            if count > 0:
                log.info(f"[+] Success: Directly downloaded {count} files.")
                return 
            else:
                log.warning("[-] No files downloaded. Switching to Git Fallback.")
        except Exception as e:
            log.warning(f"[-] Unexpected error during API download ({e}). Switching to Git Fallback.")

        log.info("[*] Executing Git Sparse-Checkout bypass strategy...")
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            self.run_command_sync(["git", "clone", "--depth", "1", "--filter=blob:none", "--sparse", GITHUB_REPO_URL, temp_dir])
            self.run_command_sync(["git", "sparse-checkout", "set", self.target_subpath], cwd=temp_dir)

            source_dir = temp_path / self.target_subpath
            if not source_dir.exists():
                raise FileNotFoundError(f"[CRITICAL] Path not found in GitHub repository either: {self.target_subpath}")

            shutil.copytree(source_dir, self.dest_dir, dirs_exist_ok=True)
            
            for init_file in self.dest_dir.rglob("__init__.py"):
                init_file.unlink()
            log.info("[+] Git Fallback extraction and cleanup completed.")

    def _execute_isolated_subtask_sync(self, command_name: str, args: list):
        """
        @role: Isolated Sync Subprocess Invoker
        @desc: Controls isolated OS processes using standard subprocess and threads without asyncio.
               This method safely blocks in a background thread and guarantees perfect sequential control.
        """
        log.signal(f"[Sub-Task] Resolving contract for isolated execution: {command_name}")
        task_info_list = registry.registered_cli_tasks.get(command_name)
        if not task_info_list:
            raise RuntimeError(f"Cannot find contract '{command_name}' in registry.")

        module_fqn = task_info_list[0].get("module_fqn")
        cmd = [sys.executable, "-m", module_fqn] + args
        log.info(f"  -> Spawning Subprocess: {' '.join(cmd)}")
        
        ## Synchronous execution of OS process (waiting to receive real-time logs via Pipe)
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(SELF_ROOT),
            text=True,
            bufsize=1
        )

        ## Internal thread worker to intercept subprocess output in real-time
        def stream_reader(stream, prefix=""):
            for line in stream:
                text = line.strip()
                if text:
                    log.info(f"  {prefix}| {text}")

        ## Start 2 lightweight read-only threads to prevent stdout and stderr from blocking each other
        t_out = threading.Thread(target=stream_reader, args=(process.stdout, ""))
        t_err = threading.Thread(target=stream_reader, args=(process.stderr, "[ERR]"))
        t_out.start()
        t_err.start()

        ## Synchronously wait for output and process termination (does not affect Node main loop)
        t_out.join()
        t_err.join()
        process.wait()
        if process.returncode != 0:
            raise RuntimeError(f"Sub-task '{command_name}' failed with return code {process.returncode}")
        
        return True

    def mutate_dependencies(self):
        """Dependency substitution based on pure Isolated Execution"""
        log.info("\n## @mutate: Isolated Subprocess Execution")
        log.signal("[TASK] Executing 'align.imports' sequentially...")
        self._execute_isolated_subtask_sync(
            command_name="align.imports", 
            args=["--local", "--old", "llama_index.core", "--new", f"{ADAPTER_PATH}", "--repo", TARGET_REPO]
        )
        
        log.signal("[TASK] Executing 'align.path' sequentially...")
        self._execute_isolated_subtask_sync(
            command_name="align.path", 
            args=["--local", "--repo", TARGET_REPO]
        )
        log.info("\n[SUCCESS] All isolated mutation processes completed.")

    def run(self):
        """Single execution pipeline (perfect synchronous control flow)"""
        if not (SELF_ROOT / TARGET_REPO).is_dir():
            log.error(f"[ERROR] Cannot find repository '{TARGET_REPO}'. Make sure it is at the top of '.self/'.")
            sys.exit(1)
            
        try:
            self.fetch()
            self.mutate_dependencies()
        except Exception as e:
            log.error(f"\n[CRITICAL ERROR] Pipeline halted: {e}")
            raise


def entry_task(args):
    parser = argparse.ArgumentParser(description="Brane LlamaIndex Integration Harvester")
    parser.add_argument("--category", required=True, help="Integration category (e.g., readers, llms)")
    parser.add_argument("--name", required=True, help="Integration name (e.g., database, openai)")
    parsed_args = parser.parse_args(args)
    runner = MutationRunner(category=parsed_args.category, name=parsed_args.name)
    return CliTaskAdapter(runner.run)


@contract.cli(
    name="llama.mutation", 
    args=["--category", "--name"],
    tags=["llama", "mutation", "harvester"],
    entry="entry_task" 
)
def main(args=None):
    if args is not None:
        return entry_task(args)
    bound_args, remain = parse_local(sys.argv[1:])
    if bound_args.local:
        entry_task(remain).run()
    else:
        dispatch_cli("llama.mutation", entry_task, __file__)

if __name__ == "__main__":
    main()