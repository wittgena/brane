# xphi.scope.surface.dphi
from contextlib import ExitStack

from anchor.provider.llm.local import LocalLM
from bound.channel.compat.switch.dsp.settings import settings
from xphi.scope.surface.config import BaseSurface, SurfaceConfig
from xphi.scope.thch import thch_scope

from watcher.plane.emitter import get_emitter

log = get_emitter("surface.dphi")

class DphiSurface(BaseSurface):
    def __init__(self, config: SurfaceConfig):
        self.config = config
        self.lm = None
        self._stack = ExitStack()

    def up(self):
        log.info(f"[*] Initializing Dphi Surface (Model: {self.config.dphi_model})...")
        self.lm = LocalLM(model=self.config.dphi_model)
        context_kwargs = {"lm": self.lm}
        if self.config.adapter is not None:
            context_kwargs["adapter"] = self.config.adapter
            
        self._stack.enter_context(settings.context(**context_kwargs))

        if self.config.use_thch:
            log.info("[*] Folding Dphi internals into ThCh Fractal...")
            self._stack.enter_context(thch_scope())

    def down(self):
        self._stack.close()
        log.info("[*] Folding Dphi Surface (Teardown)...")

    def get_engine(self):
        return lambda agent_usage: self.lm