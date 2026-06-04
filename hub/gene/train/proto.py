# hub.gene.train.proto
## @lineage: hub.memory.train.proto
## @lineage: scripts.xyz.xor.code.context.train.proto
## @lineage: spec.code.train.proto
## @lineage: spec.script.train.proto
## @lineage: foldbox.intent.proto
import inspect
import logging
from typing import Any, TextIO
from dspy.dsp.utils.settings import settings
from dspy.predict.parallel import Parallel
from dspy.primitives.example import Example
from dspy.primitives.prediction import Prediction
from dspy.utils import magicattr
from dspy.utils.callback import with_callbacks
from dspy.utils.inspect_history import pretty_print_history
from dspy.utils.usage_tracker import track_usage
from bridge.context.signature import ContextSignature
from foldbox.scope.thch import ThCh
from meta.plane.emitter import get_emitter

log = get_emitter("intent.proto")

class ProgramMeta(type):
    def __call__(cls, *args, **kwargs):
        obj = cls.__new__(cls, *args, **kwargs)
        if isinstance(obj, cls):
            IntentProto._base_init(obj)
            cls.__init__(obj, *args, **kwargs)

            if not hasattr(obj, "callbacks"):
                obj.callbacks = []
            if not hasattr(obj, "history"):
                obj.history = []
        return obj

class IntentProto(ContextSignature, metaclass=ProgramMeta):
    signature = None

    def _base_init(self):
        self._compiled = False
        self.callbacks = []
        self.history = []

    def __init__(self, callbacks=None):
        self.callbacks = callbacks or []
        self._compiled = False
        self.history = []

        if self.signature:
            self._engine = Thch(self.signature)

    def __getstate__(self):
        state = self.__dict__.copy()
        state.pop("history", None)
        state.pop("callbacks", None)
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        if not hasattr(self, "history"):
            self.history = []
        if not hasattr(self, "callbacks"):
            self.callbacks = []

    ## @hook.lifecycle
    def on_before_forward(self, *args, **kwargs):
        """[Intercept] forward 실행 직전 호출되는 접점"""
        log.signal(f"[{self.__class__.__name__}] Preparing to invoke forward...")
        return args, kwargs

    def on_after_forward(self, output: Any) -> Any:
        """[Intercept] forward 실행 직후 결과값을 조작하거나 시스템 큐(PsiEvent)에 이벤트를 발행하는 접점"""
        log.signal(f"[{self.__class__.__name__}] Forward execution completed.")
        return output
        
    async def on_before_aforward(self, *args, **kwargs):
        """비동기 실행 직전 접점"""
        return args, kwargs

    async def on_after_aforward(self, output: Any) -> Any:
        """비동기 실행 직후 접점"""
        return output
    
    def forward(self, **kwargs):
        """하위 클래스에서 forward를 재정의하지 않으면, Theoria가 캡슐화한 엔진(_engine)을 자동으로 실행"""
        if hasattr(self, '_engine') and getattr(self, '_engine'):
            return self._engine(**kwargs)
        raise NotImplementedError("Subclass must define 'signature' or override 'forward()'")


    ## 코어 파이프라인 (훅 주입)
    @with_callbacks
    def __call__(self, *args, **kwargs) -> Prediction:
        from dspy.dsp.utils.settings import thread_local_overrides
        caller_modules = settings.caller_modules or []
        caller_modules = list(caller_modules)
        caller_modules.append(self)

        with settings.context(caller_modules=caller_modules):
            ## @contact.1: 실행 전 파라미터 조작 및 우회 검사
            args, kwargs = self.on_before_forward(*args, **kwargs)

            ## 만약 on_before_forward에서 LLM 호출을 건너뛰고 Prediction을 반환했다면 바로 종료
            if isinstance(args, Prediction):
                return self.on_after_forward(args)

            if settings.track_usage and thread_local_overrides.get().get("usage_tracker") is None:
                with track_usage() as usage_tracker:
                    output = self.forward(*args, **kwargs)
                tokens = usage_tracker.get_total_tokens()
                self._set_lm_usage(tokens, output)
                
                ## @contact.2: 실행 후 결과 조작 (Usage Tracker 동작 시)
                return self.on_after_forward(output)

            ## @contact.2: 일반 실행 시 결과 조작
            output = self.forward(*args, **kwargs)
            return self.on_after_forward(output)

    @with_callbacks
    async def acall(self, *args, **kwargs) -> Prediction:
        from dspy.dsp.utils.settings import thread_local_overrides

        caller_modules = settings.caller_modules or []
        caller_modules = list(caller_modules)
        caller_modules.append(self)

        with settings.context(caller_modules=caller_modules):
            ## @contact.1: 비동기 실행 전 훅
            args, kwargs = await self.on_before_aforward(*args, **kwargs)

            if isinstance(args, Prediction):
                return await self.on_after_aforward(args)

            if settings.track_usage and thread_local_overrides.get().get("usage_tracker") is None:
                with track_usage() as usage_tracker:
                    output = await self.aforward(*args, **kwargs)
                    tokens = usage_tracker.get_total_tokens()
                    self._set_lm_usage(tokens, output)

                    ## @contact.2: 비동기 실행 후 훅 (Usage Tracker)
                    return await self.on_after_aforward(output)

            ## @contact.2: 일반 비동기 실행 시 훅
            output = await self.aforward(*args, **kwargs)
            return await self.on_after_aforward(output)

    def named_predictors(self):
        from dspy.predict.predict import Predict
        return [(name, param) for name, param in self.named_parameters() if isinstance(param, Predict)]

    def predictors(self):
        return [param for _, param in self.named_predictors()]

    def set_lm(self, lm):
        for _, param in self.named_predictors():
            param.lm = lm

    def get_lm(self):
        all_used_lms = [param.lm for _, param in self.named_predictors()]

        if len(set(all_used_lms)) == 1:
            return all_used_lms[0]

        raise ValueError("Multiple LMs are being used in the module. There's no unique LM to return.")

    def __repr__(self):
        s = []
        for name, param in self.named_predictors():
            s.append(f"{name} = {param}")
        return "\n".join(s)

    def map_named_predictors(self, func):
        for name, predictor in self.named_predictors():
            set_attribute_by_name(self, name, func(predictor))
        return self

    def inspect_history(self, n: int = 1, file: "TextIO | None" = None) -> None:
        pretty_print_history(self.history, n, file=file)

    def batch(
        self,
        examples: list[Example],
        num_threads: int | None = None,
        max_errors: int | None = None,
        return_failed_examples: bool = False,
        provide_traceback: bool | None = None,
        disable_progress_bar: bool = False,
        timeout: int = 120,
        straggler_limit: int = 3,
    ) -> list[Example] | tuple[list[Example], list[Example], list[Exception]]:
        exec_pairs = [(self, example.inputs()) for example in examples]
        parallel_executor = Parallel(
            num_threads=num_threads,
            max_errors=max_errors,
            return_failed_examples=return_failed_examples,
            provide_traceback=provide_traceback,
            disable_progress_bar=disable_progress_bar,
            timeout=timeout,
            straggler_limit=straggler_limit,
        )
        if return_failed_examples:
            results, failed_examples, exceptions = parallel_executor.forward(exec_pairs)
            return results, failed_examples, exceptions
        else:
            results = parallel_executor.forward(exec_pairs)
            return results

    def _set_lm_usage(self, tokens: dict[str, Any], output: Any):
        prediction_in_output = None
        if isinstance(output, Prediction):
            prediction_in_output = output
        elif isinstance(output, tuple) and len(output) > 0 and isinstance(output[0], Prediction):
            prediction_in_output = output[0]
        if prediction_in_output:
            prediction_in_output.set_lm_usage(tokens)
        else:
            log.warning("Failed to set LM usage. Please return `dspy.Prediction` object from dspy.Module to enable usage tracking.")

    def __getattribute__(self, name):
        attr = super().__getattribute__(name)
        if name == "forward" and callable(attr):
            stack = inspect.stack()
            forward_called_directly = len(stack) <= 1 or stack[1].function != "__call__"
            if forward_called_directly:
                log.warning(
                    f"Calling module.forward(...) on {self.__class__.__name__} directly is discouraged. "
                    f"Please use module(...) instead."
                )

        return attr

def set_attribute_by_name(obj, name, value):
    magicattr.set(obj, name, value)
