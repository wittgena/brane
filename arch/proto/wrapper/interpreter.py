# arch.proto.wrapper.interpreter
"""@desc: Local interpreter for secure Python code execution using Deno/Pyodide"""
import functools
import inspect
import json
import keyword
import os
import subprocess
import threading
from os import PathLike
from typing import Any, Callable, Mapping
from arch.proto.wrapper.code import PRIMITIVE_TYPES, ExecutionError, ProtocolError, ExecutionResult
from arch.proto.wrapper.jsonrpc import JsonRpcMessage, JsonRpcErrorCode
from watcher.plane.emitter import get_emitter

log = get_emitter(__name__)
LARGE_VAR_THRESHOLD = 100 * 1024 * 1024

class PythonInterpreter:
    def __init__(
        self,
        deno_command: list[str] | None = None,
        enable_read_paths: list[PathLike | str] | None = None,
        enable_write_paths: list[PathLike | str] | None = None,
        enable_env_vars: list[str] | None = None,
        enable_network_access: list[str] | None = None,
        sync_files: bool = True,
    ) -> None:
        if isinstance(deno_command, dict):
            raise TypeError("deno_command must be a list of strings")

        self.enable_read_paths = enable_read_paths or []
        self.enable_write_paths = enable_write_paths or []
        self.enable_env_vars = enable_env_vars or []
        self.enable_network_access = enable_network_access or []
        self.sync_files = sync_files

        if deno_command:
            self.deno_command = list(deno_command)
        else:
            args = ["deno", "run"]
            allowed_read_paths = [self._get_runner_path()]
            deno_dir = self._get_deno_dir()
            if deno_dir:
                allowed_read_paths.append(deno_dir)

            if self.enable_read_paths:
                allowed_read_paths.extend(str(p) for p in self.enable_read_paths)
            if self.enable_write_paths:
                allowed_read_paths.extend(str(p) for p in self.enable_write_paths)
            args.append(f"--allow-read={','.join(allowed_read_paths)}")

            self._env_arg = ""
            if self.enable_env_vars:
                user_vars = [str(v).strip() for v in self.enable_env_vars]
                args.append("--allow-env=" + ",".join(user_vars))
                self._env_arg = ",".join(user_vars)
            if self.enable_network_access:
                args.append(f"--allow-net={','.join(str(x) for x in self.enable_network_access)}")
            if self.enable_write_paths:
                args.append(f"--allow-write={','.join(str(x) for x in self.enable_write_paths)}")

            args.append(self._get_runner_path())
            if self._env_arg:
                args.append(self._env_arg)
            self.deno_command = args

        self.deno_process = None
        self._mounted_files = False
        self._request_id = 0
        self._owner_thread: int | None = None
        self._pending_large_vars = {}

    def _check_thread_ownership(self) -> None:
        current_thread = threading.current_thread().ident
        if self._owner_thread is None:
            self._owner_thread = current_thread
        elif self._owner_thread != current_thread:
            raise RuntimeError("PythonInterpreter is not thread-safe. Instantiate per thread.")

    @staticmethod
    @functools.lru_cache(maxsize=1)
    def _get_deno_dir() -> str | None:
        if "DENO_DIR" in os.environ:
            return os.environ["DENO_DIR"]
        try:
            result = subprocess.run(
                ["deno", "info", "--json"], capture_output=True, text=True, check=False
            )
            if result.returncode == 0:
                info = json.loads(result.stdout)
                return info.get("denoDir")
        except Exception:
            log.warning("Unable to find the Deno cache dir.")
        return None

    def _get_runner_path(self) -> str:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(current_dir, "runner.js")

    def _mount_files(self):
        if self._mounted_files:
            return
        paths_to_mount = []
        if self.enable_read_paths:
            paths_to_mount.extend(self.enable_read_paths)
        if self.enable_write_paths:
            paths_to_mount.extend(self.enable_write_paths)
        if not paths_to_mount:
            return
            
        for path in paths_to_mount:
            if not path:
                continue
            if not os.path.exists(path):
                if self.enable_write_paths and path in self.enable_write_paths:
                    open(path, "a").close()
                else:
                    raise ProtocolError(f"Cannot mount non-existent file: {path}")
            virtual_path = f"/sandbox/{os.path.basename(path)}"
            self._send_request("mount_file", {"host_path": str(path), "virtual_path": virtual_path}, f"mounting {path}")
        self._mounted_files = True

    def _sync_files(self):
        if not self.enable_write_paths or not self.sync_files:
            return
        for path in self.enable_write_paths:
            virtual_path = f"/sandbox/{os.path.basename(path)}"
            sync_msg = JsonRpcMessage.notification("sync_file", {"virtual_path": virtual_path, "host_path": str(path)})
            self.deno_process.stdin.write(sync_msg + "\n")
            self.deno_process.stdin.flush()

    def _extract_parameters(self, fn: Callable) -> list[dict]:
        sig = inspect.signature(fn)
        params = []
        for name, param in sig.parameters.items():
            p = {"name": name}
            if param.annotation != inspect.Parameter.empty:
                if param.annotation in PRIMITIVE_TYPES:
                    p["type"] = param.annotation.__name__
            if param.default != inspect.Parameter.empty:
                p["default"] = param.default
            params.append(p)
        return params

    def _register_callables(self, callables: Mapping[str, Callable[..., Any]] | None) -> None:
        """execute 시점에 주입된 호출 가능 객체를 동적으로 샌드박스에 바인딩합니다."""
        if not callables:
            return

        callables_info = []
        for name, fn in callables.items():
            callables_info.append({
                "name": name,
                "parameters": self._extract_parameters(fn)
            })

        self._send_request("register", {"tools": callables_info}, "registering callables")

    def _handle_callable_call(self, request: dict, callables: Mapping[str, Callable[..., Any]]) -> None:
        """샌드박스 내부의 호출 요청을 주입된 callable 매핑과 연결하여 실행합니다."""
        request_id = request["id"]
        params = request.get("params", {})
        callable_name = params.get("name")
        kwargs = params.get("kwargs", {})

        try:
            if callable_name not in callables:
                raise ExecutionError(f"Unknown callable: {callable_name}")
            
            result = callables[callable_name](**kwargs)
            is_json = isinstance(result, (list, dict))
            response = JsonRpcMessage.result(
                {"value": json.dumps(result) if is_json else (str(result) if result is not None else ""), "type": "json" if is_json else "string"},
                request_id
            )
        except Exception as e:
            error_type = type(e).__name__
            error_code = JsonRpcErrorCode.from_exception_type(error_type)
            response = JsonRpcMessage.error(error_code, str(e), request_id, {"type": error_type})

        self.deno_process.stdin.write(response + "\n")
        self.deno_process.stdin.flush()

    def _ensure_deno_process(self) -> None:
        if self.deno_process is None or self.deno_process.poll() is not None:
            self._mounted_files = False
            try:
                self.deno_process = subprocess.Popen(
                    self.deno_command,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="UTF-8",
                    env=os.environ.copy()
                )
            except FileNotFoundError as e:
                raise ProtocolError("Deno executable not found.") from e
            self._health_check()

    _MAX_SKIP_LINES = 100

    def _read_response_line(self, context: str) -> str:
        response_line = self.deno_process.stdout.readline().strip()
        if response_line:
            return response_line

        exit_code = self.deno_process.poll()
        if exit_code is not None:
            stderr = self.deno_process.stderr.read() if self.deno_process.stderr else ""
            raise ProtocolError(f"Deno exited (code {exit_code}) {context}: {stderr}")
        raise ProtocolError(f"No response {context}")

    def _parse_response_line(self, response_line: str, context: str) -> dict | None:
        if not response_line.startswith("{"):
            log.debug("Skipping non-JSON output during %s: %s", context, response_line)
            return None
        try:
            return json.loads(response_line)
        except json.JSONDecodeError:
            log.debug("Skipping malformed JSON during %s: %s", context, response_line[:100])
            return None

    def _send_request(self, method: str, params: dict, context: str) -> dict:
        self._request_id += 1
        request_id = self._request_id
        msg = JsonRpcMessage.request(method, params, request_id)
        self.deno_process.stdin.write(msg + "\n")
        self.deno_process.stdin.flush()

        skipped = 0
        while skipped <= self._MAX_SKIP_LINES:
            response_line = self._read_response_line(context)
            response = self._parse_response_line(response_line, context)
            if response is None:
                skipped += 1
                continue

            if response.get("id") != request_id:
                raise ProtocolError(f"Response ID mismatch {context}: expected {request_id}, got {response.get('id')}")
            if "error" in response:
                # 시스템 레벨 에러는 ProtocolError로 강제 종료
                raise ProtocolError(f"Error {context}: {response['error'].get('message', 'Unknown error')}")
            return response

        raise ProtocolError(f"Too many non-JSON lines ({skipped}) {context}")

    def _health_check(self) -> None:
        response = self._send_request("execute", {"code": "print(1+1)"}, "during health check")
        if response.get("result", {}).get("output", "").strip() != "2":
            raise ProtocolError(f"Unexpected ping response: {response}")

    def _to_json_compatible(self, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        elif isinstance(value, dict):
            return {k: self._to_json_compatible(v) for k, v in value.items()}
        elif isinstance(value, (list, tuple)):
            return [self._to_json_compatible(v) for v in value]
        elif isinstance(value, set):
            try:
                return sorted(self._to_json_compatible(v) for v in value)
            except TypeError:
                return [self._to_json_compatible(v) for v in value]
        else:
            raise ExecutionError(f"Unsupported value type: {type(value).__name__}")

    def _inject_variables(self, code: str, variables: Mapping[str, Any]) -> str:
        for key in variables:
            if not key.isidentifier() or keyword.iskeyword(key) or key == "json":
                raise ExecutionError(f"Invalid variable name: '{key}'")

        large_vars = {}
        small_assignments = []
        for k, v in variables.items():
            serialized = self._serialize_value(v)
            if len(serialized) > LARGE_VAR_THRESHOLD:
                large_vars[k] = json.dumps(self._to_json_compatible(v))
            else:
                small_assignments.append(f"{k} = {serialized}")

        self._pending_large_vars = large_vars

        if large_vars:
            # 경고: 이 하드코딩된 경로는 파일 시스템 격리 레벨에서 여전히 충돌 가능성이 있으나,
            # 현재 위상 구조 교정에 집중하기 위해 논리적 흐름만 유지합니다.
            large_assignments = [f"{k} = json.loads(open('/tmp/spi_vars/{k}.json').read())" for k in large_vars]
            assignments = ["import json"] + small_assignments + large_assignments
        else:
            assignments = small_assignments

        return "\n".join(assignments) + "\n" + code if assignments else code

    def _serialize_value(self, value: Any) -> str:
        if value is None:
            return "None"
        elif isinstance(value, str):
            return repr(value)
        elif isinstance(value, bool):
            return "True" if value else "False"
        elif isinstance(value, (int, float)):
            return str(value)
        elif isinstance(value, (list, tuple)):
            items = ", ".join(self._serialize_value(item) for item in value)
            return f"[{items}]"
        elif isinstance(value, dict):
            items = ", ".join(f"{self._serialize_value(k)}: {self._serialize_value(v)}" for k, v in value.items())
            return f"{{{items}}}"
        elif isinstance(value, set):
            try:
                sorted_items = sorted(value)
            except TypeError:
                sorted_items = list(value)
            items = ", ".join(self._serialize_value(item) for item in sorted_items)
            return f"[{items}]"
        else:
            raise ExecutionError(f"Unsupported value type: {type(value).__name__}")

    def _inject_large_var(self, name: str, value: str) -> None:
        self._send_request("inject_var", {"name": name, "value": value}, f"injecting variable '{name}'")

    def execute(
        self,
        code: str,
        variables: Mapping[str, Any] | None = None,
        callables: Mapping[str, Callable[..., Any]] | None = None,
    ) -> ExecutionResult:
        """
        주입된 데이터(variables)와 함수(callables)를 기반으로 코드를 실행합니다.
        오류가 발생하더라도 제어 흐름을 끊지 않고 ExecutionResult로 래핑하여 반환합니다.
        단, 통신/인프라 붕괴 시에는 ProtocolError를 raise합니다.
        """
        self._check_thread_ownership()
        variables = variables or {}
        callables = callables or {}
        
        try:
            code = self._inject_variables(code, variables)
        except ExecutionError as e:
            return ExecutionResult(success=False, error=e)

        self._ensure_deno_process()
        self._mount_files()
        
        self._register_callables(callables)

        for name, value in self._pending_large_vars.items():
            self._inject_large_var(name, value)

        self._request_id += 1
        execute_request_id = self._request_id
        input_data = JsonRpcMessage.request("execute", {"code": code}, execute_request_id)
        
        try:
            self.deno_process.stdin.write(input_data + "\n")
            self.deno_process.stdin.flush()
        except BrokenPipeError:
            self._ensure_deno_process()
            self._mount_files()
            self._register_callables(callables)
            for name, value in self._pending_large_vars.items():
                self._inject_large_var(name, value)
            self.deno_process.stdin.write(input_data + "\n")
            self.deno_process.stdin.flush()

        skipped = 0
        while skipped <= self._MAX_SKIP_LINES:
            output_line = self._read_response_line("during execution")
            msg = self._parse_response_line(output_line, "during execution")
            if msg is None:
                skipped += 1
                continue

            if "method" in msg:
                if msg["method"] == "tool_call":
                    self._handle_callable_call(msg, callables)
                    continue

            if "result" in msg:
                if msg.get("id") != execute_request_id:
                    raise ProtocolError(f"Response ID mismatch: expected {execute_request_id}, got {msg.get('id')}")
                
                result = msg["result"]
                self._sync_files()
                return ExecutionResult(success=True, output=result.get("output", ""))

            if "error" in msg:
                if msg.get("id") is not None and msg.get("id") != execute_request_id:
                    raise ProtocolError(f"Response ID mismatch: expected {execute_request_id}, got {msg.get('id')}")
                
                error = msg["error"]
                error_message = error.get("message", "Unknown error")
                error_data = error.get("data", {})
                error_type = error_data.get("type", "Error")

                return ExecutionResult(
                    success=False, 
                    error=ExecutionError(f"{error_type}: {error_data.get('args') or error_message}")
                )

            raise ProtocolError(f"Unexpected message format from sandbox: {msg}")

        raise ProtocolError(f"Too many non-JSON lines ({skipped}) during execution")

    def start(self) -> None:
        self._ensure_deno_process()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.shutdown()

    def __call__(
        self,
        code: str,
        variables: Mapping[str, Any] | None = None,
        callables: Mapping[str, Callable[..., Any]] | None = None,
    ) -> ExecutionResult:
        return self.execute(code, variables, callables)

    def shutdown(self) -> None:
        if self.deno_process and self.deno_process.poll() is None:
            try:
                self.deno_process.stdin.write(JsonRpcMessage.notification("shutdown") + "\n")
                self.deno_process.stdin.flush()
                self.deno_process.stdin.close()
                self.deno_process.wait(timeout=2)
            except (BrokenPipeError, subprocess.TimeoutExpired):
                self.deno_process.kill()
        self.deno_process = None
        self._owner_thread = None