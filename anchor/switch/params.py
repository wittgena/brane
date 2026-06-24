# anchor.switch.params
import os
from pydantic import BaseModel, ConfigDict
from typing import Any, Dict, Iterable, List, Optional, Union
from openai.types.responses.response_function_tool_call import ResponseFunctionToolCall

LITELLM_CONVERT_SWITCH = False

if LITELLM_CONVERT_SWITCH:
    try:
        from litellm.types.llms.openai import ResponseAPIUsage, ResponsesAPIResponse
        from litellm.types.llms.openai import ResponsesAPIStreamingResponse
        from litellm.types.llms.openai import ToolParam
        from litellm.types.llms.openai import ChatCompletionToolParam
        from litellm.types.llms.openai import OutputFunctionToolCall
        from litellm.types.llms.openai import ChatCompletionToolParamFunctionChunk
        from litellm.types.llms.openai import ResponsesAPIResponse
        from litellm.types.llms.openai import ResponsesAPIStreamEvents
        ## --- 
        from litellm.types.responses.main import GenericResponseOutputItem
        from litellm.types.rerank import RerankResponse
        from litellm.types.completion import (
            ChatCompletionMessageParam,
            ChatCompletionSystemMessageParam,
            ChatCompletionUserMessageParam,
            ChatCompletionAssistantMessageParam,
            ChatCompletionToolMessageParam,
            ChatCompletionFunctionMessageParam,
            ChatCompletionMessageToolCallParam,
            ChatCompletionContentPartParam,
            ChatCompletionMessageToolCall
        )
        from litellm.types.utils import (
            ChatCompletionDeltaToolCall,
            ChatCompletionRedactedThinkingBlock,
            CompletionTokensDetailsWrapper,
            EmbeddingResponse,
            Function,
            HiddenParams,
            ImageResponse,
            PromptTokensDetailsWrapper,
            TranscriptionUsageDurationObject,
            TranscriptionUsageTokensObject,
        )
        from litellm.types.utils import Usage
        ## ---
        from litellm.types.utils import TextChoices, TextCompletionResponse, TranscriptionResponse
        from litellm.types.utils import ChatCompletionMessageToolCall
        from litellm.types.utils import ModelResponse, ModelResponseStream, Delta, StreamingChoices, Choices, Message

        LITELLM_CONVERT_SWITCH = True
    except ImportError:
        LITELLM_CONVERT_SWITCH = False

if not LITELLM_CONVERT_SWITCH:
    try:
        from anchor.surface.legacy.llm.openai.types import ResponseAPIUsage, ResponsesAPIResponse
        from anchor.surface.legacy.llm.openai.types import ResponsesAPIStreamingResponse
        from anchor.surface.legacy.llm.openai.types import ToolParam
        from anchor.surface.legacy.llm.openai.types import ChatCompletionToolParam
        from anchor.surface.legacy.llm.openai.types import OutputFunctionToolCall
        from anchor.surface.legacy.llm.openai.types import ResponsesAPIResponse
        from anchor.surface.legacy.llm.openai.types import ChatCompletionToolParamFunctionChunk
        from anchor.surface.legacy.llm.openai.types import ResponsesAPIStreamEvents
        ## ---
        from anchor.surface.legacy.llm.types.response import GenericResponseOutputItem
        from anchor.surface.legacy.llm.types.rerank import RerankResponse
        from anchor.surface.legacy.llm.types.completion import (
            ChatCompletionMessageParam,
            ChatCompletionSystemMessageParam,
            ChatCompletionUserMessageParam,
            ChatCompletionAssistantMessageParam,
            ChatCompletionToolMessageParam,
            ChatCompletionFunctionMessageParam,
            ChatCompletionMessageToolCallParam,
            ChatCompletionContentPartParam
        )
        from anchor.surface.legacy.llm.types.utils import (
            ChatCompletionDeltaToolCall,
            ChatCompletionRedactedThinkingBlock,
            CompletionTokensDetailsWrapper,
            EmbeddingResponse,
            Function,
            HiddenParams,
            ImageResponse,
            PromptTokensDetailsWrapper,
            TranscriptionUsageDurationObject,
            TranscriptionUsageTokensObject,
        )
        from anchor.surface.legacy.llm.types.utils import Usage
        from anchor.surface.legacy.llm.types.utils import TextChoices, TextCompletionResponse, TranscriptionResponse
        from anchor.surface.legacy.llm.types.utils import ModelResponse, ModelResponseStream, Delta, StreamingChoices, Choices, Message
        from anchor.surface.legacy.llm.types.utils import ChatCompletionMessageToolCall
    except ImportError as e:
        raise ImportError(f"Failed to load fallback types from internal modules. Error: {e}")