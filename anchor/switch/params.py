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
        from bound.adapter.legacy.llm.openai.types import ResponseAPIUsage, ResponsesAPIResponse
        from bound.adapter.legacy.llm.openai.types import ResponsesAPIStreamingResponse
        from bound.adapter.legacy.llm.openai.types import ToolParam
        from bound.adapter.legacy.llm.openai.types import ChatCompletionToolParam
        from bound.adapter.legacy.llm.openai.types import OutputFunctionToolCall
        from bound.adapter.legacy.llm.openai.types import ResponsesAPIResponse
        from bound.adapter.legacy.llm.openai.types import ChatCompletionToolParamFunctionChunk
        from bound.adapter.legacy.llm.openai.types import ResponsesAPIStreamEvents
        ## ---
        from bound.adapter.legacy.llm.types.response import GenericResponseOutputItem
        from bound.adapter.legacy.llm.types.rerank import RerankResponse
        from bound.adapter.legacy.llm.types.completion import (
            ChatCompletionMessageParam,
            ChatCompletionSystemMessageParam,
            ChatCompletionUserMessageParam,
            ChatCompletionAssistantMessageParam,
            ChatCompletionToolMessageParam,
            ChatCompletionFunctionMessageParam,
            ChatCompletionMessageToolCallParam,
            ChatCompletionContentPartParam
        )
        from bound.adapter.legacy.llm.types.utils import (
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
        from bound.adapter.legacy.llm.types.utils import Usage
        from bound.adapter.legacy.llm.types.utils import TextChoices, TextCompletionResponse, TranscriptionResponse
        from bound.adapter.legacy.llm.types.utils import ModelResponse, ModelResponseStream, Delta, StreamingChoices, Choices, Message
        from bound.adapter.legacy.llm.types.utils import ChatCompletionMessageToolCall
    except ImportError as e:
        raise ImportError(f"Failed to load fallback types from internal modules. Error: {e}")