# bound.xor.dsp.model.prompter
## @lineage: meta.xor.opt.model.prompter
from typing import Any
from bound.xor.exam.example import Example
from xphi.scope.module.meta import Module

class Prompter:
    def __init__(self):
        pass

    def compile(self, student: Module, *, trainset: list[Example], teacher: Module | None = None, valset: list[Example] | None = None, **kwargs) -> Module:
        raise NotImplementedError

    def get_params(self) -> dict[str, Any]:
        return self.__dict__
