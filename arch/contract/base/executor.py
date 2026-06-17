# arch.contract.base.executor
from __future__ import annotations
import asyncio
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any, Protocol
from dataclasses import dataclass
from arch.proto.event.psi import PsiType, PsiEvent
from arch.contract.interface import IPhaseField, IBoundExecutor
from watcher.plane.emitter import get_emitter

class BaseExecutor(ABC):
    """@executor: ψ → {ψ'} (execution / dispersion / transduction)"""
    def __init__(self):
        self.log = get_emitter("base.executor", phase="EXECUTION")

    @abstractmethod
    async def execute(self, psi: PsiType) -> List[PsiType]:
        pass

class SequentialExecutor(BaseExecutor):
    """@executor.sequential: ψ → {ψ} (identity / no fan-out)"""

    async def execute(self, psi: PsiType) -> List[PsiType]:
        self.log.info(f"[exec] sequential ψ={psi.symbol}")
        return [psi]

class ParallelExecutor(BaseExecutor):
    """@executor.parallel: ψ → {ψ₁..ψₙ} (local concurrency)"""
    def __init__(self, worker_fn, max_workers: int = 4):
        super().__init__()
        self.worker_fn = worker_fn
        self.max_workers = max_workers

    async def execute(self, psi: PsiType) -> List[PsiType]:
        """worker_fn: ψ → List[ψ]"""
        self.log.info(f"[exec] parallel start ψ={psi.symbol}")

        ## fan-out 정의 (예: payload 기준 분해)
        tasks = await self._split(psi)
        semaphore = asyncio.Semaphore(self.max_workers)

        async def _run(p):
            async with semaphore:
                return await self.worker_fn(p)

        results = await asyncio.gather(*[_run(p) for p in tasks], return_exceptions=True)
        merged: List[PsiType] = []
        for r in results:
            if isinstance(r, Exception):
                self.log.error(f"[exec:error] {r}")
            elif isinstance(r, list):
                merged.extend(r)
            else:
                merged.append(r)

        self.log.info(f"[exec] parallel done fanout={len(merged)}")
        return merged

    async def _split(self, psi: PsiType) -> List[PsiType]:
        """basic.split"""
        return [psi]

class AdaptiveExecutor(BaseExecutor):
    """@executor.adaptive: ψ → strategy(select) → executor.execute"""
    def __init__(self, sequential: BaseExecutor, parallel: BaseExecutor, threshold: float = 2.0):
        super().__init__()
        self.seq = sequential
        self.par = parallel
        self.threshold = threshold

    async def execute(self, psi: PsiType) -> List[PsiType]:
        density = getattr(psi, "density", 0.0)

        if density >= self.threshold:
            self.log.signal(f"[exec] switch → parallel (density={density:.2f})")
            return await self.par.execute(psi)

        return await self.seq.execute(psi)

class ScriptExecutor(IBoundExecutor):
    """@role: ∂Φ actuator (script 기반)"""

    def __init__(self, script_path: Path):
        self.script_path = script_path

    async def execute(self, field: IPhaseField) -> bool:
        if not self.script_path.exists():
            log.warning("[∂Φ] missing")
            return False

        subprocess.run(["chmod", "+x", self.script_path])
        subprocess.Popen(["bash", str(self.script_path)])

        log.info("[∂Φ] executed")
        return True
