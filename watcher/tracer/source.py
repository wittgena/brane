# watcher.tracer.source
## @lineage: phase.watcher.tracer.source
## @lineage: meta.watcher.tracer.source
## @lineage: phase.receptor.tracer.source
## @lineage: cognitive.receptor.tracer.source
"""@flow: Environment(Sync) → SourceTracer(Membrane) → Reload(Plasticity) → Ψ(PhaseSurface)"""
import time
import asyncio
import sys
import importlib
import traceback
from pathlib import Path
from watchdog.events import FileSystemEventHandler
from typing import Dict, List, Optional
from phase.runtime.receptor.topos import ReceptorTopos
from watcher.plane.emitter import get_emitter

log = get_emitter("tracer.source")

class TracerSource(FileSystemEventHandler):
    """@desc: 물리적 파일 시스템의 변이를 감지하여 런타임 위상을 갱신하고 파동을 주입"""
    
    def __init__(self, surface: ReceptorTopos, loop: asyncio.AbstractEventLoop, watch_dir: str):
        self.surface = surface
        self.loop = loop  
        self.watch_dir = Path(watch_dir).resolve()
        self.last_trigger = 0

    def _resolve_fqn(self, file_path: str) -> str:
        """물리적 파일 경로를 논리적 위상(Fully Qualified Name)으로 변환"""
        path = Path(file_path).resolve()
        try:
            relative = path.relative_to(self.watch_dir)
            return ".".join(relative.with_suffix("").parts)
        except ValueError:
            return ""

    def on_modified(self, event):
        if time.time() - self.last_trigger < 1.0:
            return

        if not (event.src_path.endswith(".py") or event.src_path.endswith(".kt")):
            return

        self.last_trigger = time.time()
        print(f"\n✨ [SourceTracer] Physical mutation detected → {event.src_path}")

        module_fqn = self._resolve_fqn(event.src_path)
        payload = {"signal_id": "unknown_mutation", "value": 0.0}

        if module_fqn and module_fqn in sys.modules:
            try:
                ## Modification (위상 갱신 / 핫 리로딩 시도)
                print(f"[Plasticity] Re-aligning topology for: {module_fqn}")
                importlib.reload(sys.modules[module_fqn])
                print(f"[Modification] {module_fqn} successfully integrated into Runtime.")
                
                payload = {
                    "signal_id": "topology_reloaded",
                    "value": 1.0,  # 긍정적 결합 파동
                    "module": module_fqn
                }
            except Exception as e:
                ## 문법 오류(SyntaxError)나 로직 오류로 인한 런타임 붕괴 방지
                print(f"[Cleavage] Critical syntax/logic error in {module_fqn}.")
                print(f"  ↳ System protected. Malformed phase rejected.")
                print(traceback.format_exc()) # 파지의 시체를 로그로만 출력하고 런타임은 보존
                
                payload = {
                    "signal_id": "mutation_rejected",
                    "value": -1.0, # 부정적 거부 파동 (Tension 상승)
                    "error": str(e)
                }
        else:
            ## 아직 런타임에 로드되지 않은 새로운 파일의 감지
            print(f"[Genesis] New structure detected: {module_fqn or event.src_path}")
            payload = {"signal_id": "new_structure_detected", "value": 0.5, "module": module_fqn}

        asyncio.run_coroutine_threadsafe(
            self.surface.emit_psi("xphi_analysis_event", payload=payload),
            self.loop
        )