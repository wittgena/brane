# swarm.trace.scope.manager
from abc import ABC, abstractmethod
import os
import subprocess
import sys
import time
import threading
import httpx
import socket
import redis
from dataclasses import dataclass
from typing import Optional
from phase.bind.client.engine.local import LLMEngine
from phase.bind.resolver import resolve_path
from watcher.plane.emitter import get_emitter
from contextlib import ExitStack
from gov.scope.dsp import settings
from agent.llm.factory.state import GraphEngine
from meta.xor.adapter.lm.local import LocalLM
from gov.scope.thch import thch_scope
from gov.scope.surface.config import BaseSurface, SurfaceConfig, get_free_port
from gov.scope.surface.dphi import DphiSurface
from gov.scope.surface.sandbox import SandboxSurface

RES_ROOT = resolve_path("res")
log = get_emitter("scope.manager")

class LocalSurface(BaseSurface):
    def __init__(self):
        self.engine = LLMEngine()

    def up(self):
        log.info("[*] Initializing Local Direct Surface...")
        self.engine.ensure_server()
        start_time = time.time()
        ready = False
        try:
            time.sleep(2) 
            ready = True
        except Exception:
            log.debug(f"[-] Wait interrupted during Local Surface init: {e}")

        if not ready:
            log.warning("[-] Local Engine might not be fully ready, proceeding anyway.")

    def down(self):
        log.info("[*] Folding Local Surface...")

    def get_engine(self):
        return lambda agent_usage: self.engine

class SurfaceManager:
    def __init__(self, config: SurfaceConfig):
        self.config = config
        if config.use_sandbox:
            self.impl = SandboxSurface(config)
        elif config.use_dphi:
            self.impl = DphiSurface(config)
        else:
            self.impl = LocalSurface()

    def __enter__(self):
        self.impl.up()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.impl.down()
        log.info("[+] Context Manager: Surface closed.")

    def get_engine(self):
        return self.impl.get_engine()

def managed_scope(**kwargs):
    config = SurfaceConfig(**kwargs)
    return SurfaceManager(config)

if __name__ == "__main__":
    with managed_scope(use_dphi=True) as manager:
        lm = manager.get_engine()(agent_usage=None)
        model_name = "unknown"
        if hasattr(lm, "kwargs"):
            model_name = lm.kwargs.get("model", "unknown")
            
        log.info(f"Surface is active. Active LM: {model_name}")