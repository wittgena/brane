# phase.ator.reflect.sensor
## @lineage: phase.activator.sensor
## @lineage: phase.bind.activator.sensor
## @lineage: cognitive.activator.sensor
## @lineage: phase.bound.activator.sensor
## @lineage: arch.activator.sensor
"""
@desc: Lazy-binding environment observer; resolves local topology and binds external IO surfaces
@flow: sense -> resolve -> select -> bind → emit
"""
import json
import os
import sys
import hashlib
import socket
import subprocess
import logging
from datetime import datetime
from abc import ABC, abstractmethod
from pathlib import Path
from watcher.plane.emitter import get_emitter
from arch.contract.registry.unified import cli_contract
from phase.bind.resolver import find_current_self, resolve_path, load_bound

log = get_emitter('reflect.sensor')

try:
    SELF_ROOT = find_current_self()
    ANCHOR_ROOT = resolve_path("anchor")
    LIB_ROOT = resolve_path("lib")
    BOUND_CONFIG = load_bound(SELF_ROOT) 
except Exception as e:
    log.error(f"[error] 기준면(self)을 찾을 수 없음: {e}")
    sys.exit(1)

class Sensor(ABC):
    @abstractmethod
    def sense(self) -> dict:
        pass

class Binder(ABC):
    @abstractmethod
    def bind(self, target: Path, source: str) -> str:
        pass

class SpaceSensor(Sensor):
    """Detects spatial constraints (container, permissions, anchor presence)"""
    def sense(self) -> dict:
        return {
            "type": "space",
            "is_container": os.path.exists('/.dockerenv'),
            "self_anchor": SELF_ROOT.exists(),
            "permissions": {
                "uid": os.getuid(),
                "writable": os.access(SELF_ROOT, os.W_OK) if SELF_ROOT.exists() else False
            }
        }

class RuntimeSensor(Sensor):
    def __init__(self):
        self.lib_root = LIB_ROOT

    """Captures execution identity; hashes artifacts as stable signatures"""
    def sense(self) -> dict:
        jars = sorted(self.lib_root.glob("xphi-*.jar"))
        if not jars:
            raise RuntimeError("xphi jar not found")

        bins = { "xphi": jars[-1] }
        identity = {}
        for name, path in bins.items():
            if path and path.exists():
                with open(path, "rb") as f:
                    identity[name] = hashlib.sha256(f.read()).hexdigest()[:12]
            else:
                identity[name] = None
        
        return {
            "type": "runtime",
            "java": self._get_java_v(),
            "self_identity": identity
        }

    def _get_java_v(self) -> str | None:
        try:
            return subprocess.check_output(["java", "-version"], stderr=subprocess.STDOUT).decode().splitlines()[0]
        except Exception:
            return None

class PythonSensor(Sensor):
    """Local interpreter surface; minimal runtime context"""
    def sense(self) -> dict:
        return {
            "version": sys.version.split()[0],
            "executable": sys.executable,
            "is_venv": sys.prefix != sys.base_prefix
        }

class InfraSensor(Sensor):
    """External infra probing; detects reachable services as latent connections"""
    def sense(self) -> dict:
        is_k8s = 'KUBERNETES_SERVICE_HOST' in os.environ
        return {
            "kubernetes": {"detected": is_k8s},
            "external_db": {
                "redis": self._check_port('localhost', 6379),
                "mongo": self._check_port('localhost', 27017)
            }
        }

    def _check_port(self, host: str, port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.2)
            return s.connect_ex((host, port)) == 0

class CloudBinder:
    """Resolves external IO endpoints; selects cloud or fallback substrate"""
    def __init__(self):
        self.dropbox = [os.path.expanduser("~/Dropbox"), os.path.expanduser("~/Library/CloudStorage/Dropbox")]
        self.gdrive = [os.path.expanduser("~/Google Drive"), os.path.expanduser("~/Library/CloudStorage/GoogleDrive")]

    def resolve_io(self) -> str:
        """Cache prefers persistent cloud; falls back to ephemeral tmp"""
        return next((p for p in self.dropbox if os.path.exists(p)), "/tmp/io")

    def resolve_memory(self) -> str:
        """Memory prefers persistent cloud; falls back to ephemeral tmp"""
        return next((p for p in self.gdrive if os.path.exists(p)), "/tmp/memory")

class SystemBinder(Binder):
    """Applies binding (link/mount); materializes external → local mapping"""
    def bind(self, target: Path, source: str) -> str:
        if not target or not source:
            return "skipped"
        # TODO: 실제 바인딩(Symlink 등) 구현
        return "success"

class ToposScanner:
    """Aggregates sensor outputs into a unified topology snapshot"""
    def __init__(self, sensors: list[Sensor]):
        self.sensors = sensors

    def scan(self) -> dict:
        return {s.__class__.__name__: s.sense() for s in self.sensors}

class SensorBootstrap:
    def __init__(self, scanner: ToposScanner, cloud: CloudBinder, binder: Binder):
        self.scanner = scanner
        self.cloud = cloud
        self.binder = binder

    def bootstrap(self) -> dict:
        ## step.1: Observe current phase (partial, distributed signals)
        topology = self.scanner.scan()

        ## step.2: Collapse abstract paths into concrete anchor-relative targets.
        io_target = resolve_path("io")
        memory_target = resolve_path("memory")

        ## step.3: Select external substrate (cloud vs tmp)
        io_src = self.cloud.resolve_io()
        memory_src = self.cloud.resolve_memory()
        cache_status = True
        log_status = True
        ## step.4: Materialize binding (ext -> local anchor)
        # cache_status = self.binder.bind(io_target, io_src)
        # log_status = self.binder.bind(memory_target, memory_src)
        return {
            "topology": topology,
            "binding": {
                "io": {
                    "target": str(io_target) if io_target else None,
                    "source": io_src,
                    "status": cache_status
                },
                "memory": {
                    "target": str(memory_target) if memory_target else None,
                    "source": memory_src,
                    "status": log_status
                }
            },
            ## Channel namespace projection from schema
            "bound_channels": BOUND_CONFIG.get("channels", {}).get("namespaces", []),
            "observed_at": datetime.now().isoformat()
        }

@cli_contract(name="sensor_ready", args=["--repo", "meta"], tags=["bootstrap", "sensor"])
def main():
    sensors = [SpaceSensor(), RuntimeSensor(), PythonSensor(), InfraSensor()]
    boot = SensorBootstrap(scanner=ToposScanner(sensors), cloud=CloudBinder(), binder=SystemBinder())
    print(json.dumps(boot.bootstrap(), indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
    