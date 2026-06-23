# anchor.model.token.convert
## @lineage: anchor.router.model.token.convert
## @lineage: bound.router.model.token.convert
## @lineage: bound.channel.model.token.convert
## @lineage: channel.model.token.convert
## @lineage: bound.token.convert
## @lineage: channel.bound.token.convert
## @lineage: gate.bound.token.convert
## @lineage: blm.bound.token.convert
## @lineage: blm.frag.token.convert
## @lineage: blm.convert_message
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Literal,
    Mapping,
    Optional,
    Tuple,
    Type,
    Union,
    cast,
    get_args,
)
from pydantic import BaseModel
from anchor.model.llm.types.openai import AllMessageValues

def convert_list_message_to_dict(messages: List):
    new_messages = []
    for message in messages:
        convert_msg_to_dict = cast(AllMessageValues, convert_to_dict(message))
        cleaned_message = cleanup_none_field_in_message(message=convert_msg_to_dict)
        new_messages.append(cleaned_message)
    return new_messages

def convert_to_dict(message: Union[BaseModel, dict]) -> dict:
    if isinstance(message, BaseModel):
        return message.model_dump(exclude_none=True)
    elif isinstance(message, dict):
        return message
    else:
        raise TypeError(f"Invalid message type: {type(message)}. Expected dict or Pydantic model.")