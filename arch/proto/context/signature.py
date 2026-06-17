# arch.proto.context.signature
from pydantic import BaseModel, Field
from typing import Any

def In(desc: str = "", **kwargs) -> Any:
    """순수 Pydantic Field를 이용한 입력 필드 마커"""
    return Field(json_schema_extra={"__meta_field_type": "input", "desc": desc, **kwargs})

def Out(desc: str = "", **kwargs) -> Any:
    """순수 Pydantic Field를 이용한 출력 필드 마커"""
    return Field(json_schema_extra={"__meta_field_type": "output", "desc": desc, **kwargs})

class ProtoSignature(BaseModel):
    pass