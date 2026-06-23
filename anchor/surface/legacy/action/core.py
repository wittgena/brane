# anchor.surface.legacy.action.core
from typing import Any, Dict, List, Optional, Union
from anchor.switch.params import ModelResponse, ModelResponseStream
from anchor.surface.legacy.action.preprocessor import CompletionPreprocessor
from anchor.surface.legacy.types.mapping.exception import exception_type
from anchor.model.provider.adapter.registry import AdapterRegistry
from bound.transport.stream.wrapper import CustomStreamWrapper
from watcher.plane.emitter import get_emitter

log = get_emitter("action.core")

async def async_core_completion(
    model: str,
    messages: List = [],
    **kwargs,
) -> Union[ModelResponse, CustomStreamWrapper]:
    if model is None:
        raise ValueError("model param not passed in.")

    ## 전처리 실행
    preprocessor = CompletionPreprocessor(model=model, messages=messages, kwargs=kwargs)
    ctx = preprocessor.build()
    log.debug(f"[bound.completion] 코어 진입: model={ctx.model}, provider={ctx.custom_llm_provider}")

    try:
        adapter = AdapterRegistry.get_adapter(ctx.custom_llm_provider)
        response = adapter.execute(ctx)
        if ctx.stream is True and isinstance(response, ModelResponseStream):
            return CustomStreamWrapper(
                completion_stream=response, model=ctx.model, custom_llm_provider=ctx.custom_llm_provider, logging_obj=ctx.logging_obj,
            )
        return response
    except Exception as e:
        log.error(f"[bound.completion] 코어 엔진 예외 발생: {str(e)}")
        if ctx.logging_obj:
            ctx.logging_obj.post_call(
                input=ctx.messages, api_key=ctx.api_key, original_response=str(e), additional_args={"headers": ctx.headers},
            )
        
        error_completion_kwargs = {"model": model, "messages": messages, **ctx.original_kwargs}
        raise exception_type(
            model=ctx.model, custom_llm_provider=ctx.custom_llm_provider, original_exception=e,
            completion_kwargs=error_completion_kwargs, extra_kwargs=ctx.original_kwargs,
        )