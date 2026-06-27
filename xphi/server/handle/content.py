# xphi.server.handle.content
## @lineage: bound.bridge.server.handle.content
## @lineage: bound.server.xphi.handle.content
## @lineage: bound.server.handle.content
## @lineage: bound.server.mcps.handle.content
## @lineage: anchor.mcp.server.handle.content
from urllib.parse import urlparse

from anchor.surface.mcps.types import (
    PaginatedRequestParams,
    ListResourcesResult,
    ListPromptsResult,
    Resource,
    ReadResourceResult,
    ReadResourceRequestParams,
    TextResourceContents,
    Prompt, 
    PromptArgument,
    GetPromptResult, 
    GetPromptRequestParams
)
from anchor.surface.mcps.server.lowlevel.server import Server
from bound.transport.session.context import ServerRequestContext

mcp_config = {"transport": "stdio"}
SAMPLE_RESOURCES = {
    "greeting": {"title": "Welcome Message", "content": "Hello! This is a sample text resource."},
    "help": {"title": "Help Documentation", "content": "This server provides sample text resources."},
}
PAGINATED_ITEMS = [f"Item {i}" for i in range(1, 101)]

async def handle_list_resources(ctx: ServerRequestContext, params: PaginatedRequestParams | None) -> ListResourcesResult:
    """정적 리소스와 페이지네이션이 적용된 아이템 목록을 함께 반환합니다."""
    ## 정적 리소스 (첫 페이지에만 표시)
    start = int(params.cursor) if params and params.cursor else 0
    resources = [
        Resource(uri=f"file:///{name}.txt", name=name, title=data["title"], mime_type="text/plain")
        for name, data in SAMPLE_RESOURCES.items()
    ] if start == 0 else []

    ## 페이지네이션 리소스 (10개씩 분할)
    page_size = 10
    end = start + page_size
    resources.extend([
        Resource(uri=f"resource://items/{item}", name=item, description=f"Description for {item}")
        for item in PAGINATED_ITEMS[start:end]
    ])
    
    next_cursor = str(end) if end < len(PAGINATED_ITEMS) else None
    return ListResourcesResult(resources=resources, next_cursor=next_cursor)

async def handle_read_resource(ctx: ServerRequestContext, params: ReadResourceRequestParams) -> ReadResourceResult:
    """요청된 URI에 해당하는 리소스 내용을 반환합니다."""
    parsed = urlparse(str(params.uri))
    name = parsed.path.replace(".txt", "").lstrip("/")

    ## 정적 리소스 처리
    if name in SAMPLE_RESOURCES:
        content = SAMPLE_RESOURCES[name]["content"]
    ## 페이지네이션 아이템 처리 (resource://items/Item X)
    elif str(params.uri).startswith("resource://items/"):
        content = f"Detailed content for {name}"
    else:
        raise ValueError(f"Unknown resource: {params.uri}")

    return ReadResourceResult(
        contents=[TextResourceContents(uri=str(params.uri), text=content, mime_type="text/plain")]
    )

async def handle_list_prompts(ctx: ServerRequestContext, params: PaginatedRequestParams | None) -> ListPromptsResult:
    return ListPromptsResult(
        prompts=[
            Prompt(
                name="simple",
                title="Simple Assistant Prompt",
                description="A simple prompt with optional arguments",
                arguments=[
                    PromptArgument(name="context", description="Additional context", required=False),
                    PromptArgument(name="topic", description="Specific topic", required=False),
                ],
            )
        ]
    )

async def handle_get_prompt(ctx: ServerRequestContext, params: GetPromptRequestParams) -> GetPromptResult:
    if params.name != "simple":
        raise ValueError(f"Unknown prompt: {params.name}")
    
    args = params.arguments or {}
    messages = []
    if args.get("context"):
        messages.append(types.PromptMessage(role="user", content=types.TextContent(type="text", text=f"Context: {args['context']}")))
    
    topic_text = f"the following topic: {args.get('topic')}" if args.get("topic") else "whatever questions I may have."
    messages.append(types.PromptMessage(role="user", content=types.TextContent(type="text", text=f"Please help me with {topic_text}")))

    return GetPromptResult(messages=messages, description="Generated prompt messages")

mcp = Server(
    "mcp-content-server",
    on_list_resources=handle_list_resources,
    on_read_resource=handle_read_resource,
    on_list_prompts=handle_list_prompts,
    on_get_prompt=handle_get_prompt,
)