# bound.adapter.provider.state.mapper
## @lineage: bound.adapter.provider.state.rule
import os
import json
import asyncio
import functools
from pathlib import Path
from typing import AsyncGenerator, Generator, Any, List

from bound.adapter.llama.base.llms.types import ChatMessage, MessageRole
from arch.proto.phase.gate import uuid4 
from phase.bind.resolver import get_invoker
from watcher.plane.emitter import get_emitter

_invoker_full, MODULE_NAMESPACE = get_invoker(Path(__file__))
log = get_emitter(MODULE_NAMESPACE, phase="SYSTEM")

class StateMapper:
    """
    @delegate: State Translation Rule Engine
    @desc: 
    - 캡슐화된 상태 변환, 향후 독립적인 Rule 파일로 분리될 수 있도록 설계
    - LlamaIndex 규격과 Brane(OpenAI 호환) 규격 간의 양방향 매핑 및 데이터 누수 복원을 담당
    """
    @staticmethod
    def to_llama_messages(messages: List[dict]) -> List[ChatMessage]:
        """Brane Context Messages -> LlamaIndex ChatMessage"""
        llama_messages = []
        for msg in messages:
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
        return llama_messages

    @staticmethod
    def to_openai_choice(response: Any, req_id: str, logger: Any) -> dict:
        """LlamaIndex ChatResponse -> OpenAI Compatible Choice Dict (with Anomaly Recovery)"""
        message_content = response.message.content or ""
        tool_calls = response.message.additional_kwargs.get("tool_calls", None)
        
        ## @rule: Role Missing Guard
        ## LlamaIndex 응답에서 role이 누락되거나 None인 경우 기본값인 'assistant'로 강제 바인딩
        role_val = response.message.role.value if hasattr(response.message, "role") and response.message.role else "assistant"

        ## @rule: Gemini Function Call Leak Recovery Guard
        ## LlamaIndex integration이 파싱하지 못한 원본 구글 SDK의 툴 호출을 낚아채어 복원
        if not tool_calls and hasattr(response, "raw") and response.raw:
            try:
                raw_resp = response.raw
                content = raw_resp.get("content", {}) if isinstance(raw_resp, dict) else getattr(raw_resp, "content", None)
                if content:
                    parts = content.get("parts", []) if isinstance(content, dict) else getattr(content, "parts", [])
                    if parts and len(parts) > 0:
                        first_part = parts[0]
                        f_call = first_part.get("function_call") if isinstance(first_part, dict) else getattr(first_part, "function_call", None)
                        
                        if f_call:
                            f_name = f_call.get("name") if isinstance(f_call, dict) else getattr(f_call, "name", None)
                            f_args = f_call.get("args") if isinstance(f_call, dict) else getattr(f_call, "args", None)
                            
                            if f_name:
                                tool_calls = [{
                                    "id": f"call_{str(uuid4())[:8]}",
                                    "type": "function",
                                    "function": {
                                        "name": f_name,
                                        "arguments": json.dumps(f_args) if isinstance(f_args, dict) else str(f_args)
                                    }
                                }]
                                logger.debug(f"[InterLLM-{req_id}] 🎯 [MappingRule] Reconstructed leaked tool_call: {f_name}")
            except Exception as e:
                logger.warning(f"[InterLLM-{req_id}] ⚠️ [MappingRule] Raw fallback parsing failed: {e}")

        ## @bind: OpenAI 호환 구조체 최종 조립
        choice_data = {
            "index": 0,
            "message": {
                "role": role_val,
                "content": message_content,
            },
            "finish_reason": "stop"
        }
        if tool_calls:
            choice_data["message"]["tool_calls"] = tool_calls
            choice_data["finish_reason"] = "tool_calls"
        return choice_data