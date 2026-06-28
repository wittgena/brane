# bound.adapter.provider.inter
## @lineage: bound.bridge.provider.inter
## @lineage: xphi.adapter.provider.inter
## @lineage: anchor.model.provider.adapter.inter
"""
@manifold: Universal Bridge Adapter
@flow: CompletionContext (Brane) -> LLMRouter (Projection) -> LlamaIndex (Execution) -> ModelResponse (Resolution)
@desc: Dynamically binds Brane contexts to LlamaIndex topologies, ensuring bi-directional state translation.
"""
from typing import AsyncGenerator, Generator
from bound.adapter.llama.base.llms.types import ChatMessage, MessageRole
from bound.router.adapter.llm import LLMRouter
from bound.transport.stream.wrapper import CustomStreamWrapper
from bound.adapter.provider.base import BaseProviderAdapter
from anchor.channel.client.action.preprocessor import CompletionContext

class InterLLMAdapter(BaseProviderAdapter):
    """
    @manifold: Universal Bridge Adapter
    @desc: 
    - Dynamically projects Brane's `CompletionContext` into the LlamaIndex topology via `LLMRouter`
    - ensuring seamless bi-directional translation of states, schemas, and streams
    """
    def __init__(self):
        self.router = LLMRouter()

    async def execute(self, ctx: CompletionContext):
        ## @phase: Topological Projection (Dynamic Instantiation)
        llama_kwargs = {
            "api_key": ctx.api_key,
            "api_base": ctx.api_base,
            "temperature": ctx.optional_params.get("temperature", 0.7),
            "max_tokens": ctx.optional_params.get("max_tokens"),
            "timeout": ctx.timeout if isinstance(ctx.timeout, (int, float)) else 60.0,
        }
        
        ## @bind: Merge residual vectors to maintain context integrity
        for k, v in ctx.optional_params.items():
            if k not in llama_kwargs:
                llama_kwargs[k] = v

        ## @purge: Drop null vectors to preserve target LLM's native boundaries
        llama_kwargs = {k: v for k, v in llama_kwargs.items() if v is not None}

        try:
            llm = self.router.route_and_load(model_name=ctx.model, **llama_kwargs)
        except Exception as e:
            raise RuntimeError(f"[LlamaBridge] 모델 인스턴스 생성 실패: {e}")

        ## @phase: State Mapping (Context Dict -> ChatMessage)
        llama_messages = []
        for msg in ctx.messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            llama_messages.append(ChatMessage(role=MessageRole(role), content=content))

        ## @phase: Execution & Boundary Resolution
        if ctx.stream:
            ## @bifurcate: Stream execution based on concurrency state
            if ctx.acompletion:
                response_stream = await llm.astream_chat(llama_messages)
            else:
                response_stream = llm.stream_chat(llama_messages)
            
            ## @unwrap: Expose raw temporal chunks to align with Brane's stream topology
            async def stream_generator():
                if ctx.acompletion:
                    async for chunk in response_stream:
                        yield chunk.raw
                else:
                    for chunk in response_stream:
                        yield chunk.raw

            ## @wrap: Encapsulate into Brane's standard stream boundary
            return CustomStreamWrapper(
                completion_stream=stream_generator(), 
                model=ctx.model, 
                custom_llm_provider=ctx.custom_llm_provider, 
                logging_obj=ctx.logging_obj
            )
        else:
            ## @execute: Singular state execution
            if ctx.acompletion:
                response = await llm.achat(llama_messages)
            else:
                response = llm.chat(llama_messages)
            
            ## @resolve: Extract core payload and inject into Brane's ModelResponse boundary
            raw_response = response.raw
            if hasattr(raw_response, "model_dump"):
                for key, value in raw_response.model_dump().items():
                    setattr(ctx.model_response, key, value)
            elif isinstance(raw_response, dict):
                for key, value in raw_response.items():
                    setattr(ctx.model_response, key, value)
                    
            return ctx.model_response