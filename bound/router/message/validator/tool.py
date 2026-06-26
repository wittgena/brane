# bound.router.message.validator.tool
## @lineage: xphi.server.validation
## @lineage: bound.server.validation
## @lineage: bound.adapter.mcps.stdio.validation
from anchor.surface.mcps.shared.exceptions import MCPError
from anchor.surface.mcps.types import INVALID_PARAMS, ClientCapabilities, SamplingMessage, Tool, ToolChoice

def check_sampling_tools_capability(client_caps: ClientCapabilities | None) -> bool:
    if client_caps is None:
        return False
    if client_caps.sampling is None:
        return False
    if client_caps.sampling.tools is None:
        return False
    return True

def validate_sampling_tools(
    client_caps: ClientCapabilities | None,
    tools: list[Tool] | None,
    tool_choice: ToolChoice | None,
) -> None:
    if tools is not None or tool_choice is not None:
        if not check_sampling_tools_capability(client_caps):
            raise MCPError(code=INVALID_PARAMS, message="Client does not support sampling tools capability")

def validate_tool_use_result_messages(messages: list[SamplingMessage]) -> None:
    if not messages:
        return

    last_content = messages[-1].content_as_list
    has_tool_results = any(c.type == "tool_result" for c in last_content)

    previous_content = messages[-2].content_as_list if len(messages) >= 2 else None
    has_previous_tool_use = previous_content and any(c.type == "tool_use" for c in previous_content)

    if has_tool_results:
        # Per spec: "SamplingMessage with tool result content blocks
        # MUST NOT contain other content types."
        if any(c.type != "tool_result" for c in last_content):
            raise ValueError("The last message must contain only tool_result content if any is present")
        if previous_content is None:
            raise ValueError("tool_result requires a previous message containing tool_use")
        if not has_previous_tool_use:
            raise ValueError("tool_result blocks do not match any tool_use in the previous message")

    if has_previous_tool_use and previous_content:
        tool_use_ids = {c.id for c in previous_content if c.type == "tool_use"}
        tool_result_ids = {c.tool_use_id for c in last_content if c.type == "tool_result"}
        if tool_use_ids != tool_result_ids:
            raise ValueError("ids of tool_result blocks and tool_use blocks from previous message do not match")
