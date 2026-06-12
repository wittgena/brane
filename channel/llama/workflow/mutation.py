# channel.llama.workflow.mutation
## @lineage: anchor.workflow.mutation
## @lineage: meta.anchor.workflow.mutation
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
from watcher.plane.emitter import get_emitter
from phase.runtime.cli.executor import CliTaskAdapter, parse_local, dispatch_cli

log = get_emitter("workflow.mutation", phase="SYSTEM")

try:
    SELF_ROOT = find_current_self()
except Exception as e:
    log.error(f"[error] 기준면(.self)을 찾을 수 없음: {e}")
    sys.exit(1)

DEST_REPO = "brane"
GITHUB_API_BASE = "https://api.github.com/repos/run-llama/llama_index/contents"
GITHUB_REPO_URL = "https://github.com/run-llama/llama_index.git"

class MutationRunner:
    """GitHub API 추출 및 순수 동기 서브 프로세스(Isolated OS Process) 오케스트레이터"""
    
    def __init__(self, category: str, name: str):
        self.category = category
        self.name = name
        self.target_subpath = f"llama-index-integrations/{category}/llama-index-{category}-{name}/llama_index/{category}/{name}"
        self.dest_dir = SELF_ROOT / DEST_REPO / "channel" / "llama" / category / name

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

    def fetch_reader(self):
        log.info(f"=== [Phase 1] Extract: '{self.category}/{self.name}' 추출 ===")
        log.info(f"[*] 합성된 원본 경로: {self.target_subpath}")
        
        self.dest_dir.mkdir(parents=True, exist_ok=True)
        api_target_url = f"{GITHUB_API_BASE}/{self.target_subpath}"

        try:
            log.info("[*] GitHub API를 통한 파일 단위 추출 시도...")
            count = self._download_via_api(api_target_url, self.dest_dir)
            if count > 0:
                log.info(f"[+] 성공: {count}개의 파일을 직접 다운로드했습니다.")
                return 
            else:
                log.warning("[-] 다운로드된 파일이 없습니다. Git Fallback으로 전환합니다.")
        except Exception as e:
            log.warning(f"[-] API 다운로드 중 예기치 않은 오류 ({e}). Git Fallback으로 전환합니다.")

        log.info("[*] Git Sparse-Checkout 우회 전략 실행...")
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            self.run_command_sync(["git", "clone", "--depth", "1", "--filter=blob:none", "--sparse", GITHUB_REPO_URL, temp_dir])
            self.run_command_sync(["git", "sparse-checkout", "set", self.target_subpath], cwd=temp_dir)

            source_dir = temp_path / self.target_subpath
            if not source_dir.exists():
                raise FileNotFoundError(f"[CRITICAL] Github 저장소에서도 경로를 찾을 수 없습니다: {self.target_subpath}")

            shutil.copytree(source_dir, self.dest_dir, dirs_exist_ok=True)
            
            for init_file in self.dest_dir.rglob("__init__.py"):
                init_file.unlink()
            log.info("[+] Git Fallback 추출 및 세척 완료.")

    # -------------------------------------------------------------------------
    # [아키텍처 혁신 구간] 순수 동기 스레드 기반 격리 서브 프로세스 제어
    # -------------------------------------------------------------------------
    def _execute_isolated_subtask_sync(self, command_name: str, args: list):
        """
        @role: Isolated Sync Subprocess Invoker
        @desc: asyncio 없이 표준 subprocess와 thread를 사용하여 독립된 OS 프로세스를 통제합니다.
               이 메서드는 백그라운드 스레드에서 안전하게 블로킹되며 순차 제어를 완벽히 보장합니다.
        """
        log.signal(f"[Sub-Task] Resolving contract for isolated execution: {command_name}")
        
        task_info_list = registry.registered_cli_tasks.get(command_name)
        if not task_info_list:
            raise RuntimeError(f"레지스트리에서 '{command_name}' 계약을 찾을 수 없습니다.")

        module_fqn = task_info_list[0].get("module_fqn")
        cmd = [sys.executable, "-m", module_fqn] + args
        log.info(f"  -> Spawning Subprocess: {' '.join(cmd)}")
        
        # OS 프로세스 동기 실행 (Pipe를 통해 실시간 로그 수신 대기)
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(SELF_ROOT),
            text=True,
            bufsize=1 # Line-buffered
        )

        # 서브 프로세스의 출력을 실시간으로 가로채는 내부 스레드 워커
        def stream_reader(stream, prefix=""):
            for line in stream:
                text = line.strip()
                if text:
                    log.info(f"  {prefix}| {text}")

        # stdout과 stderr가 서로 블로킹되지 않도록 가벼운 읽기 전용 스레드 2개 가동
        t_out = threading.Thread(target=stream_reader, args=(process.stdout, ""))
        t_err = threading.Thread(target=stream_reader, args=(process.stderr, "[ERR]"))
        t_out.start()
        t_err.start()

        # 출력과 프로세스 종료를 동기적으로 완벽히 대기 (Node 메인 루프에는 영향 없음)
        t_out.join()
        t_err.join()
        process.wait()

        if process.returncode != 0:
            raise RuntimeError(f"Sub-task '{command_name}' failed with return code {process.returncode}")
        
        return True

    def mutate_dependencies(self):
        """순수 Isolated Execution 기반의 의존성 치환"""
        log.info("\n=== [Phase 2] Mutate: Isolated Subprocess Execution ===")

        # 동기 호출이므로 자연스럽게 순차 실행(Sequential)이 보장됩니다.
        # (만약 병렬 실행이 필요하다면 concurrent.futures.ThreadPoolExecutor를 사용하면 됩니다)
        
        log.signal("[TASK] Executing 'align.imports' sequentially...")
        self._execute_isolated_subtask_sync(
            command_name="align.imports", 
            args=["--local", "--old", "llama_index.core", "--new", "channel.llama.core", "--repo", DEST_REPO]
        )
        
        log.signal("[TASK] Executing 'align.path' sequentially...")
        self._execute_isolated_subtask_sync(
            command_name="align.path", 
            args=["--local", "--repo", DEST_REPO]
        )

        log.info("\n[SUCCESS] 모든 격리된 변이 프로세스가 완료되었습니다.")

    def run(self):
        """단일 실행 파이프라인 (완벽한 동기 제어 흐름)"""
        if not (SELF_ROOT / DEST_REPO).is_dir():
            log.error(f"[ERROR] '{DEST_REPO}' 레포지토리를 찾을 수 없습니다. '.self/' 최상단인지 확인하세요.")
            sys.exit(1)
            
        try:
            self.fetch_reader()
            self.mutate_dependencies()  # 비동기(asyncio.run) 제거, 순수 동기 호출
            
        except Exception as e:
            log.error(f"\n[CRITICAL ERROR] 파이프라인 중단: {e}")
            raise  # 예외를 상위(CliTaskAdapter)로 던져 정상적으로 FAILED 상태를 반환하도록 함

def entry_task(args):
    parser = argparse.ArgumentParser(description="Brane LlamaIndex Integration Harvester")
    parser.add_argument("--category", required=True, help="Integration category (e.g., readers, llms)")
    parser.add_argument("--name", required=True, help="Integration name (e.g., database, openai)")
    parsed_args = parser.parse_args(args)
    
    runner = MutationRunner(category=parsed_args.category, name=parsed_args.name)
    return CliTaskAdapter(runner.run)

@contract.cli(
    name="workflow.mutation", 
    args=["--category", "--name"],
    tags=["workflow", "mutation", "harvester"],
    entry="entry_task" 
)
def main(args=None):
    if args is not None:
        return entry_task(args)
        
    bound_args, remain = parse_local(sys.argv[1:])
    if bound_args.local:
        entry_task(remain).run()
    else:
        dispatch_cli("workflow.mutation", entry_task, __file__)

if __name__ == "__main__":
    main()