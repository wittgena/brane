# anchor.switch.params
## @lineage: anchor.router.switch.params
import os
from pydantic import BaseModel, ConfigDict
from typing import Any, Dict, Iterable, List, Optional, Union
from openai.types.responses.response_function_tool_call import ResponseFunctionToolCall

USE_LITELLM_STRICT_TYPES = False

if USE_LITELLM_STRICT_TYPES:
    try:
        from litellm.types.llms.openai import ResponseAPIUsage, ResponsesAPIResponse
        from litellm.types.llms.openai import ChatCompletionToolParam
        from litellm.types.llms.openai import OutputFunctionToolCall
        from litellm.types.llms.openai import ChatCompletionToolParamFunctionChunk
        from litellm.types.llms.openai import ResponsesAPIResponse
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

        USE_LITELLM_STRICT_TYPES = True
    except ImportError:
        USE_LITELLM_STRICT_TYPES = False

if not USE_LITELLM_STRICT_TYPES:
    try:
        from bound.channel.model.types.llms.openai import ResponseAPIUsage, ResponsesAPIResponse
        from bound.channel.model.types.llms.openai import ChatCompletionToolParam
        from bound.channel.model.types.llms.openai import OutputFunctionToolCall
        from bound.channel.model.types.llms.openai import ResponsesAPIResponse
        from bound.channel.model.types.llms.openai import ChatCompletionToolParamFunctionChunk
        ## ---
        from bound.channel.model.types.responses.main import GenericResponseOutputItem
        from bound.channel.model.types.rerank import RerankResponse
        from bound.channel.model.types.completion import (
            ChatCompletionMessageParam,
            ChatCompletionSystemMessageParam,
            ChatCompletionUserMessageParam,
            ChatCompletionAssistantMessageParam,
            ChatCompletionToolMessageParam,
            ChatCompletionFunctionMessageParam,
            ChatCompletionMessageToolCallParam,
            ChatCompletionContentPartParam
        )
        from bound.channel.model.types.utils import (
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
        from bound.channel.model.types.utils import Usage
        ## -- 
        from litellm.types.utils import TextChoices, TextCompletionResponse, TranscriptionResponse
        from litellm.types.utils import ModelResponse, ModelResponseStream, Delta, StreamingChoices, Choices, Message
        from litellm.types.utils import ChatCompletionMessageToolCall
    except ImportError as e:
        raise ImportError(f"Failed to load fallback types from internal blm.types modules. Error: {e}")

class CompletionRequest(BaseModel):
    model: str
    messages: List[ChatCompletionMessageParam] = []
    timeout: Optional[Union[float, int]] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    n: Optional[int] = None
    stream: Optional[bool] = None
    stop: Optional[dict] = None
    max_tokens: Optional[int] = None
    presence_penalty: Optional[float] = None
    frequency_penalty: Optional[float] = None
    logit_bias: Optional[dict] = None
    user: Optional[str] = None
    response_format: Optional[dict] = None
    seed: Optional[int] = None
    tools: Optional[List[str]] = None
    tool_choice: Optional[str] = None
    logprobs: Optional[bool] = None
    top_logprobs: Optional[int] = None
    deployment_id: Optional[str] = None
    functions: Optional[List[str]] = None
    function_call: Optional[str] = None
    base_url: Optional[str] = None
    api_version: Optional[str] = None
    api_key: Optional[str] = None
    model_list: Optional[List[str]] = None
    model_config = ConfigDict(protected_namespaces=(), extra="allow")