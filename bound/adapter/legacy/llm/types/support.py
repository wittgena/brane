# bound.adapter.legacy.llm.types.support
## @lineage: anchor.surface.legacy.llm.types.support
## @lineage: anchor.surface.legacy.types.support
from typing_extensions import TypedDict
from typing import Literal, Optional

class ProviderSpecificModelInfo(TypedDict, total=False):
    supports_system_messages: Optional[bool]
    supports_response_schema: Optional[bool]
    supports_vision: Optional[bool]
    supports_function_calling: Optional[bool]
    supports_tool_choice: Optional[bool]
    supports_assistant_prefill: Optional[bool]
    supports_prompt_caching: Optional[bool]
    supports_computer_use: Optional[bool]
    supports_audio_input: Optional[bool]
    supports_embedding_image_input: Optional[bool]
    supports_audio_output: Optional[bool]
    supports_pdf_input: Optional[bool]
    supports_native_streaming: Optional[bool]
    supports_native_structured_output: Optional[bool]
    supports_parallel_function_calling: Optional[bool]
    supports_web_search: Optional[bool]
    supports_reasoning: Optional[bool]
    supports_url_context: Optional[bool]
    supports_none_reasoning_effort: Optional[bool]
    supports_minimal_reasoning_effort: Optional[bool]
    supports_low_reasoning_effort: Optional[bool]
    supports_xhigh_reasoning_effort: Optional[bool]
    supports_max_reasoning_effort: Optional[bool]
    supports_output_config: Optional[bool]
    supports_image_size: Optional[bool]
    bedrock_output_config_effort_ceiling: Optional[
        Literal["low", "medium", "high", "max", "xhigh"]
    ]