# xphi.flow.scanner.llm
## @lineage: anchor.rule.llama.scanner.llm
import os
import sys
import ast
import importlib
import inspect
import json
import urllib.request
import argparse
from pathlib import Path
from typing import Dict, Any

from bound.adapter.base.llms.base import BaseLLM 
from watcher.plane.emitter import get_emitter
from arch.contract.registry.unified import contract
from phase.runtime.cli.executor import CliTaskAdapter, parse_local, dispatch_cli

log = get_emitter("scanner.llm", phase="SYSTEM")

class LLMScanner:
    """Dual-mode LLM scanner for both local installed modules and remote integration catalogs"""
    
    KNOWN_LLM_BASES = {
        "BaseLLM", "LLM", "CustomLLM", 
        "FunctionCallingLLM", "OpenAILike", "MultiModalLLM"
    }

    GITHUB_LLMS_API = "https://api.github.com/repos/run-llama/llama_index/contents/llama-index-integrations/llms"

    def __init__(self, base_path: str):
        self.base_path = Path(base_path)

    ## @desc: Extract fully qualified module name from a file path safely
    def _get_module_path(self, file_path: Path) -> str:
        try:
            parts = file_path.parts
            return ".".join(parts).replace(".py", "")
        except Exception as e:
            log.error(f"[ERROR] Failed to parse module path: {file_path} - {e}")
            return ""

    ## @desc: Retrieve the list of available integrations from the official LlamaIndex repository
    def _scan_remote_catalog(self) -> Dict[str, Dict[str, Any]]:
        log.info("[*] Fetching remote LLM catalog from GitHub...")
        registry = {}
        req = urllib.request.Request(self.GITHUB_LLMS_API, headers={'User-Agent': 'Theoria-Mutation-Agent'})
        
        try:
            with urllib.request.urlopen(req) as response:
                items = json.loads(response.read().decode())
                for item in items:
                    if item.get("type") == "dir" and item.get("name", "").startswith("llama-index-llms-"):
                        llm_name = item["name"].replace("llama-index-llms-", "")
                        registry[llm_name] = {
                            "status": "available_for_mutation",
                            "source_repo": item.get("html_url"),
                            "type": "remote_catalog",
                            "tags": [llm_name]
                        }
            log.info(f"[+] Acquired {len(registry)} remote module catalogs.")
            return registry
        except Exception as e:
            log.error(f"[-] Remote scan failed: {e}")
            return {}

    ## @desc: Scan the local file system for installed LLM modules using AST and dynamic inspection
    def _scan_local_installed(self) -> Dict[str, Dict[str, Any]]:
        log.info("[*] Scanning locally installed LLM modules...")
        registry = {}
        
        if not self.base_path.exists():
            log.warning(f"[-] Base path not found: {self.base_path}")
            return registry

        ## Target strictly 'base.py' to avoid triggering circular dependencies in peripheral files
        for file_path in self.base_path.rglob("base.py"):
            module_path = self._get_module_path(file_path)
            if not module_path:
                continue

            provider_key = file_path.parent.name
            found_class_info = None

            ## Step 1: AST-based Static Scan (Fast Path)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    tree = ast.parse(f.read())
                
                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef):
                        base_names = [b.id for b in node.bases if isinstance(b, ast.Name)]
                        if any(name in self.KNOWN_LLM_BASES for name in base_names):
                            found_class_info = {
                                "status": "installed",
                                "module": module_path,
                                "class": node.name,
                                "type": "local_ast_scanned",
                                "tags": [provider_key]
                            }
                            break
            except Exception as e:
                log.debug(f"[AST Warning] Fallback to dynamic inspection due to parse failure: {e}")

            ## Step 2: Dynamic Inspection (Safe Path)
            if not found_class_info:
                try:
                    module = importlib.import_module(module_path)
                    for name, obj in inspect.getmembers(module, inspect.isclass):
                        if issubclass(obj, BaseLLM) and obj is not BaseLLM:
                            found_class_info = {
                                "status": "installed",
                                "module": module_path,
                                "class": name,
                                "type": "local_dynamic_scanned",
                                "tags": [provider_key]
                            }
                            break
                except ImportError as e:
                    log.debug(f"[Import Warning] Skipped due to missing dependencies ({module_path}): {e}")
                except Exception as e:
                    log.error(f"[Inspect Error] Fatal error during dynamic scan ({module_path}): {e}")

            if found_class_info:
                registry[provider_key] = found_class_info

        return registry

    def scan(self, target: str = "local") -> Dict[str, Dict[str, Any]]:
        if target == "remote":
            return self._scan_remote_catalog()
        elif target == "local":
            return self._scan_local_installed()
        else:
            raise ValueError(f"[ERROR] Unsupported target: {target}")


def entry_task(args):
    parser = argparse.ArgumentParser(description="Brane LlamaIndex LLM Scanner")
    parser.add_argument("--target", type=str, choices=["local", "remote"], default="local", help="Scan target: 'local' or 'remote'")
    parser.add_argument("--base-path", type=str, default="brane/channel/bridge/llms", help="Base directory for local scan")
    parsed_args = parser.parse_args(args)

    ## @desc: Execution closure wrapped by CliTaskAdapter
    def _execute_scan():
        ## Ensure current directory is in sys.path for dynamic imports
        current_dir = str(Path.cwd())
        if current_dir not in sys.path:
            sys.path.insert(0, current_dir)

        scanner = LLMScanner(base_path=parsed_args.base_path)
        try:
            result = scanner.scan(target=parsed_args.target)
            print(f"\n[{parsed_args.target.upper()} SCAN RESULT]\n{json.dumps(result, indent=2, ensure_ascii=False)}")
        except Exception as e:
            log.error(f"[ERROR] Scanner execution failed: {e}")
            sys.exit(1)

    return CliTaskAdapter(_execute_scan)


@contract.cli(
    name="llama.scanner.llm", 
    args=["--target", "--base-path"],
    tags=["llama", "scanner", "llm"],
    entry="entry_task" 
)
def main(args=None):
    if args is not None:
        return entry_task(args)
    
    bound_args, remain = parse_local(sys.argv[1:])
    if bound_args.local:
        entry_task(remain).run()
    else:
        dispatch_cli("llama.scanner.llm", entry_task, __file__)

if __name__ == "__main__":
    main()