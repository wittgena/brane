# bound.adapter.provider.inter
"""
@manifold: Universal Bridge Adapter
@flow: CompletionContext (Brane) -> LLMRouter (Projection) -> LlamaIndex (Execution) -> ModelResponse (Resolution)
@desc: Dynamically binds Brane contexts to LlamaIndex topologies, ensuring bi-directional state translation.
"""
import os
import asyncio
import functools
from pathlib import Path
from typing import AsyncGenerator, Generator

from anchor.surface.provider.routing.locator import get_llm_provider
from bound.adapter.llama.base.llms.types import ChatMessage, MessageRole
from bound.router.adapter.llm import LLMRouter, TopologyMissingError
from bound.transport.stream.wrapper import CustomStreamWrapper
from bound.adapter.provider.base import BaseProviderAdapter
from bound.channel.client.action.preprocessor import CompletionContext

from arch.proto.phase.gate import uuid4 
from phase.bind.resolver import find_current_self, get_invoker
from watcher.plane.emitter import get_emitter

_invoker_full, MODULE_NAMESPACE = get_invoker(Path(__file__))
log = get_emitter(MODULE_NAMESPACE, phase="SYSTEM")

class InterLLMAdapter(BaseProviderAdapter):
    def __init__(self):
        self.router = LLMRouter()

    async def execute(self, ctx: CompletionContext):
        req_id = str(uuid4())[:8]
        log.debug(f"[InterLLM-{req_id}] 🚀 execute START | model={ctx.model}, provider={ctx.custom_llm_provider}, stream={ctx.stream}, async={ctx.acompletion}")

        ## @phase: Environment & Credential Shim
        resolved_api_key = ctx.api_key
        if not resolved_api_key or resolved_api_key == "not-needed":
            try:
                _, _, dynamic_key, _ = get_llm_provider(
                    model=ctx.model,
                    custom_llm_provider=ctx.custom_llm_provider
                )
                if dynamic_key:
                    log.debug(f"[InterLLM-{req_id}] 🔑 API Key resolved dynamically via Locator.")
                    resolved_api_key = dynamic_key
            except Exception as e:
                log.warning(f"[InterLLM-{req_id}] ⚠️ Locator key resolution bypassed/failed: {e}")

        ## @phase: Parameter Separation (Init vs Execution)
        execution_kwargs = {}
        if "tools" in ctx.optional_params:
            execution_kwargs["tools"] = ctx.optional_params.pop("tools")
        if "tool_choice" in ctx.optional_params:
            execution_kwargs["tool_choice"] = ctx.optional_params.pop("tool_choice")

        ## @phase: Topological Projection (Dynamic Instantiation)
        llama_kwargs = {
            "api_key": resolved_api_key,
            "api_base": ctx.api_base,
            "temperature": ctx.optional_params.get("temperature", 0.7),
            "max_tokens": ctx.optional_params.get("max_tokens"),
            "timeout": ctx.timeout if isinstance(ctx.timeout, (int, float)) else 60.0,
        }
        
        ## @bind: Merge residual vectors
        for k, v in ctx.optional_params.items():
            if k not in llama_kwargs:
                llama_kwargs[k] = v

        ## @purge: Drop null vectors and dummy keys to preserve native boundaries
        llama_kwargs = {k: v for k, v in llama_kwargs.items() if v is not None and v != "not-needed"}
        safe_kwargs = {k: v for k, v in llama_kwargs.items() if not k.startswith("api_")}
        log.debug(f"[InterLLM-{req_id}] ⚙️ Routing Init kwargs: {safe_kwargs}")
        log.debug(f"[InterLLM-{req_id}] ⚙️ Routing Exec kwargs: {list(execution_kwargs.keys())}")

        try:
            llm = self.router.route_and_load(
                model_name=ctx.model, 
                custom_llm_provider=ctx.custom_llm_provider, 
                **llama_kwargs
            )
            log.debug(f"[InterLLM-{req_id}] ✅ LLM Topology Loaded: {type(llm).__name__}")
        except TopologyMissingError as te:
            log.error(f"[InterLLM-{req_id}] 🚨 TopologyMissingError: {te}")
            raise te
        except Exception as e:
            log.error(f"[InterLLM-{req_id}] 🚨 [LlamaBridge] 모델 인스턴스 생성 실패: {e}", exc_info=True)
            raise RuntimeError(f"[LlamaBridge] 모델 인스턴스 생성 실패: {e}")

        ## @phase: State Mapping (Context Dict -> ChatMessage)
        llama_messages = []
        for msg in ctx.messages:
            role = msg.get("role", "user")
            raw_content = msg.get("content", "")
            parsed_content = ""
            if isinstance(raw_content, str):
                parsed_content = raw_content
            elif isinstance(raw_content, list):
                text_chunks = []
                for block in raw_content:
                    if hasattr(block, "get"):  # dict 형태
                        if block.get("type") == "text":
                            text_chunks.append(block.get("text", ""))
                    elif hasattr(block, "text"):  # TextContent 같은 객체 형태
                        text_chunks.append(block.text)
                    elif isinstance(block, str):
                        text_chunks.append(block)
                parsed_content = "".join(text_chunks)
            else:
                parsed_content = str(raw_content)
                
            llama_messages.append(ChatMessage(role=MessageRole(role), content=parsed_content))
            
        log.debug(f"[InterLLM-{req_id}] 📝 State Mapping Complete: {len(llama_messages)} messages translated.")

        ## @phase: Execution & Boundary Resolution
        if ctx.stream:
            log.debug(f"[InterLLM-{req_id}] 🌊 Initiating STREAM Execution")
            if ctx.acompletion:
                response_stream = await llm.astream_chat(llama_messages, **execution_kwargs)
            else:
                response_stream = llm.stream_chat(llama_messages, **execution_kwargs)
            
            async def stream_generator():
                if ctx.acompletion:
                    async for chunk in response_stream:
                        yield chunk.raw
                else:
                    for chunk in response_stream:
                        yield chunk.raw

            log.debug(f"[InterLLM-{req_id}] 🔄 Returning CustomStreamWrapper")
            return CustomStreamWrapper(
                completion_stream=stream_generator(), 
                model=ctx.model, 
                custom_llm_provider=ctx.custom_llm_provider, 
                logging_obj=ctx.logging_obj
            )
        else:
            log.debug(f"[InterLLM-{req_id}] ⚡ Initiating SINGULAR Execution")
            if ctx.acompletion:
                response = await llm.achat(llama_messages, **execution_kwargs)
            else:
                import asyncio
                import functools
                chat_func = functools.partial(llm.chat, llama_messages, **execution_kwargs)
                response = await asyncio.to_thread(chat_func)
            
            log.debug(f"[InterLLM-{req_id}] ✅ Execution Complete. Resolving response boundary.")
            
            message_content = response.message.content or ""
            tool_calls = response.message.additional_kwargs.get("tool_calls", None)
            
            ## OpenAI 호환 'choices' 배열 조립
            choice_data = {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": message_content,
                },
                "finish_reason": "stop"
            }
            
            ## 도구 호출(Tool Calls)이 존재할 경우 규격에 맞게 바인딩
            if tool_calls:
                choice_data["message"]["tool_calls"] = tool_calls
                choice_data["finish_reason"] = "tool_calls"
                
            ## Brane 컨텍스트에 주입
            ctx.model_response.choices = [choice_data]
            
            ## Usage 메트릭이 있다면 함께 번역 (없으면 0으로 처리)
            ## ctx.model_response.usage = ... 
            log.debug(f"[InterLLM-{req_id}] 🏁 execute END. Returning ctx.model_response (Content Length: {len(message_content)}, Tools: {len(tool_calls) if tool_calls else 0})")
            return ctx.model_response