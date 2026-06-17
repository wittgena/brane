# phase.runtime.surface.actuator
## @lineage: phase.node.surface.actuator
import asyncio
import random
import time
import re
from arch.proto.event.psi import PsiType
from phase.bind.resolver import resolve_pattern
from watcher.plane.emitter import get_emitter

class SurfaceActuator:
    KEY_PARTS = [
        "intensity",
        "threshold",
        "state",
        "score",
        "generated",
        "flag",
        "signal",
    ]
    CONTROL_KEY = "runtime:control:emit"

    def __init__(self, sinks):
        if not isinstance(sinks, list):
            sinks = [sinks]

        self.sinks = sinks
        self.emit_enabled = True
        self.processed = 0

        ## watcher namespace alignment
        self.watcher_pattern = resolve_pattern()
        self.watcher_regex = re.compile(self.watcher_pattern)
        self.namespaces = self._extract_namespaces(self.watcher_pattern)

        ## @bind.observability
        self.log = get_emitter("surface.actuator", phase="ACTUATION") 

    def _extract_namespaces(self, pattern: str):
        inner = pattern.split("(")[1].split(")")[0]
        return inner.split("|")

    async def is_emit_enabled(self):
        for sink in self.sinks:
            try:
                val = await sink.get_control_flag(self.CONTROL_KEY)
                if val is not None:
                    return val != "off"
            except Exception:
                pass

        return self.emit_enabled

    async def _fanout_set(self, key, payload):
        await asyncio.gather(
            *(sink.set(key, payload) for sink in self.sinks),
            return_exceptions=True
        )

    async def _fanout_delete(self, key):
        await asyncio.gather(
            *(sink.delete(key) for sink in self.sinks),
            return_exceptions=True
        )

    async def actuate_psi(self, psi: PsiType):
        if not await self.is_emit_enabled():
            return

        key = psi.tag
        payload = {
            "ts": time.time(),
            "source": "runtime.loop",
            "psi": psi.symbol,
        }

        try:
            if psi.kind.endswith("removed"):
                await self._fanout_delete(key)
                self.log.signal(f"[emit] delete {key}")
            else:
                await self._fanout_set(key, payload)
                if psi.kind.endswith("added") or psi.kind.endswith("generated"):
                    self.log.signal(f"[emit] set {key}")
                else:
                    self.log.signal(f"[emit] update {key}")
            self.processed += 1
        except Exception as e:
            self.log.error(f"[emit:error] {e}")

    def random_key(self):
        ns = random.choice(self.namespaces)
        part = random.choice(self.KEY_PARTS)
        idx = random.randint(1, 5)
        return f"{ns}:{part}:{idx}"

    async def random_surface(self, duration: int = 60):
        print("## Runtime Psi Random Surface")
        print("namespaces:", self.namespaces)
        print()

        created = set()
        start = time.time()
        while time.time() - start < duration:
            if random.random() < 0.65:
                key = self.random_key()
                payload = {
                    "ts": time.time(),
                    "source": "runtime.random",
                    "v": random.random()
                }

                await self._fanout_set(key, payload)
                created.add(key)
                print(f"[ψ+] create {key}")
            else:
                if created:
                    key = random.choice(list(created))
                    await self._fanout_delete(key)
                    created.remove(key)
                    print(f"[ψ-] delete {key}")
            await asyncio.sleep(random.uniform(0.25, 0.8))
        print("\n[random surface finished]")

    async def close(self):
        for sink in self.sinks:
            try:
                await sink.close()
            except Exception:
                pass