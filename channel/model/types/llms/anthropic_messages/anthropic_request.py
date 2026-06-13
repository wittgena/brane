# channel.model.types.llms.anthropic_messages.anthropic_request
## @lineage: anchor.model.types.llms.anthropic_messages.anthropic_request
## @lineage: gate.model.types.llms.anthropic_messages.anthropic_request
## @lineage: gate.types.llms.anthropic_messages.anthropic_request
## @lineage: blm.types.llms.anthropic_messages.anthropic_request
from typing import Optional

from pydantic import BaseModel


class AnthropicMetadata(BaseModel):
    """
    Object with allowed fields for Anthropic API metadata

    https://docs.anthropic.com/en/api/messages#body-metadata-user-id
    """

    user_id: Optional[str] = None
