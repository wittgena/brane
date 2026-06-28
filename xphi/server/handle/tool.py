# xphi.server.handle.tool
## @lineage: bound.bridge.server.handle.tool
## @lineage: bound.server.xphi.handle.tool
## @lineage: bound.server.handle.tool
## @lineage: bound.server.mcps.handle.tool
## @lineage: anchor.mcp.server.handle.tool
import anyio

from anchor.surface.mcps.server.lowlevel.server import Server
from bound.transport.session.context import ServerRequestContext
from xphi.xor.store.event import InMemoryEventStore
from mcp_types import (
    PaginatedRequestParams,
    ListToolsResult,
    Tool,
    CallToolRequestParams,
    CallToolResult,
    TextContent,
)

from watcher.plane.emitter import get_emitter

log = get_emitter("handle.tool")

mcp_config = {
    "transport": "streamable-http",
    "port": 3000,
    "event_store": InMemoryEventStore(),
    "retry_interval": 100,
    "uvicorn_kwargs": {
        "log_level": "info",
    }
}

async def handle_list_tools(
    ctx: ServerRequestContext, params: PaginatedRequestParams | None
) -> ListToolsResult:
    """사용 가능한 모든 도구(Tools)의 목록을 반환합니다."""
    return ListToolsResult(
        tools=[
            # Tool 1: Notification Stream
            Tool(
                name="start-notification-stream",
                description="Sends a stream of notifications with configurable count and interval",
                input_schema={
                    "type": "object",
                    "required": ["interval", "count", "caller"],
                    "properties": {
                        "interval": {
                            "type": "number",
                            "description": "Interval between notifications in seconds",
                        },
                        "count": {
                            "type": "number",
                            "description": "Number of notifications to send",
                        },
                        "caller": {
                            "type": "string",
                            "description": "Identifier of the caller to include in notifications",
                        },
                    },
                },
            ),
            # Tool 2: Process Batch
            Tool(
                name="process_batch",
                description=(
                    "Process a batch of items with periodic checkpoints. "
                    "Demonstrates SSE polling where server closes stream periodically."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "items": {
                            "type": "integer",
                            "description": "Number of items to process (1-100)",
                            "default": 10,
                        },
                        "checkpoint_every": {
                            "type": "integer",
                            "description": "Close stream after this many items (1-20)",
                            "default": 3,
                        },
                    },
                },
            )
        ]
    )


async def handle_call_tool(ctx: ServerRequestContext, params: CallToolRequestParams) -> CallToolResult:
    """클라이언트의 Tool 호출 요청을 처리하여 적절한 로직으로 라우팅합니다."""
    arguments = params.arguments or {}

    if params.name == "start-notification-stream":
        interval = arguments.get("interval", 1.0)
        count = arguments.get("count", 5)
        caller = arguments.get("caller", "unknown")

        for i in range(count):
            notification_msg = f"[{i + 1}/{count}] Event from '{caller}' - Use Last-Event-ID to resume if disconnected"
            await ctx.session.send_log_message(
                level="info",
                data=notification_msg,
                logger="notification_stream",
                related_request_id=ctx.request_id,
            )
            log.debug(f"Sent notification {i + 1}/{count} for caller: {caller}")
            if i < count - 1:
                await anyio.sleep(interval)

        if hasattr(ctx.session, "send_resource_updated"):
            try:
                await ctx.session.send_resource_updated(uri="http:///test_resource")
            except Exception as e:
                log.debug(f"Could not send resource update: {e}")

        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=f"Sent {count} notifications with {interval}s interval for caller: {caller}",
                )
            ]
        )

    elif params.name == "process_batch":
        items = arguments.get("items", 10)
        checkpoint_every = arguments.get("checkpoint_every", 3)

        if items < 1 or items > 100:
            return CallToolResult(content=[TextContent(type="text", text="Error: items must be between 1 and 100")])
        if checkpoint_every < 1 or checkpoint_every > 20:
            return CallToolResult(content=[TextContent(type="text", text="Error: checkpoint_every must be between 1 and 20")])

        await ctx.session.send_log_message(
            level="info",
            data=f"Starting batch processing of {items} items...",
            logger="process_batch",
            related_request_id=ctx.request_id,
        )

        for i in range(1, items + 1):
            await anyio.sleep(0.5)

            await ctx.session.send_log_message(
                level="info",
                data=f"[{i}/{items}] Processing item {i}",
                logger="process_batch",
                related_request_id=ctx.request_id,
            )

            # Checkpoint 로직: 클라이언트 재연결(Polling) 유도
            if i % checkpoint_every == 0 and i < items:
                await ctx.session.send_log_message(
                    level="info",
                    data=f"Checkpoint at item {i} - closing SSE stream for polling",
                    logger="process_batch",
                    related_request_id=ctx.request_id,
                )
                if hasattr(ctx, "close_sse_stream") and ctx.close_sse_stream:
                    log.info(f"Closing SSE stream at checkpoint {i}")
                    await ctx.close_sse_stream()
                
                await anyio.sleep(0.2)

        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=f"Successfully processed {items} items with checkpoints every {checkpoint_every} items",
                )
            ]
        )
    return CallToolResult(content=[TextContent(type="text", text=f"Unknown tool: {params.name}")])

mcp = Server(
    "mcp-merged-demo-server",
    on_list_tools=handle_list_tools,
    on_call_tool=handle_call_tool,
)