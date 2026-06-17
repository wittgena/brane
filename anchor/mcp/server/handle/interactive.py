# anchor.mcp.server.handle.interactive
import uuid
from pydantic import BaseModel, Field
from mcp.server.mcpserver import Context, MCPServer
from mcp.shared.exceptions import UrlElicitationRequiredError
from mcp.types import ElicitRequestURLParams

mcp_config = {"transport": "stdio"}
mcp = MCPServer(name="mcp-interactive-server")

class BookingPreferences(BaseModel):
    """Schema for collecting user preferences."""
    checkAlternative: bool = Field(description="Would you like to check another date?")
    alternativeDate: str = Field(default="2024-12-26", description="Alternative date (YYYY-MM-DD)")

@mcp.tool()
async def book_table(date: str, time: str, party_size: int, ctx: Context) -> str:
    """Book a table with date availability check (Form Elicitation)."""
    if date == "2024-12-25":
        result = await ctx.elicit(
            message=f"No tables available for {party_size} on {date}. Try another date?",
            schema=BookingPreferences,
        )
        if result.action == "accept" and result.data:
            return f"[SUCCESS] Booked for {result.data.alternativeDate}" if result.data.checkAlternative else "[CANCELLED] No booking made"
        return "[CANCELLED] Booking cancelled"
    return f"[SUCCESS] Booked for {date} at {time}"

@mcp.tool()
async def secure_payment(amount: float, ctx: Context) -> str:
    """Process a secure payment requiring URL confirmation (URL Elicitation)."""
    elicitation_id = str(uuid.uuid4())
    result = await ctx.elicit_url(
        message=f"Please confirm payment of ${amount:.2f}",
        url=f"https://payments.example.com/confirm?amount={amount}&id={elicitation_id}",
        elicitation_id=elicitation_id,
    )
    if result.action == "accept":
        return f"Payment of ${amount:.2f} initiated - check your browser to complete"
    return "Payment cancelled"

@mcp.tool()
async def connect_service(service_name: str, ctx: Context) -> str:
    """Connect to a third-party service requiring OAuth authorization."""
    elicitation_id = str(uuid.uuid4())
    raise UrlElicitationRequiredError([
        ElicitRequestURLParams(
            mode="url",
            message=f"Authorization required to connect to {service_name}",
            url=f"https://{service_name}.example.com/oauth/authorize?elicit={elicitation_id}",
            elicitation_id=elicitation_id,
        )
    ])