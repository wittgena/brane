# arch.topos.state.surge
## @lineage: topos.medium.subst.surge
from pydantic import BaseModel, model_validator, ConfigDict
from typing import Any, Type, TypeVar
import dataclasses

T = TypeVar("T", bound="SurgeBaseModel")

def _melt_alien_objects(obj: Any) -> Any:
    """이종 네임스페이스에서 온 모든 실체(Instance)를 순수 데이터 질료(Primitive)로 해체"""
    ## 블루프린트(Type) 보존: 클래스 자체는 융해하지 않고 그대로 통과
    if isinstance(obj, type):
        return obj

    ## 컨테이너 재귀 순회 (Collection Mapping)
    if isinstance(obj, dict):
        return {k: _melt_alien_objects(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple, set)):
        return type(obj)(_melt_alien_objects(v) for v in obj)

    ## Pydantic 융해 (v1, v2 호환)
    if hasattr(obj, 'model_dump') and callable(getattr(obj, 'model_dump')):
        return _melt_alien_objects(obj.model_dump())
    if hasattr(obj, 'dict') and callable(getattr(obj, 'dict')):
        return _melt_alien_objects(obj.dict())

    ## 표준 Dataclass 융해
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return _melt_alien_objects(dataclasses.asdict(obj))

    ## 일반 Python 객체 융해 (Optional) - __dict__를 가진 일반 객체 중 시스템 내부 객체인 경우 데이터로 취급
    if hasattr(obj, "__dict__") and str(type(obj).__module__).startswith(("agent", "closure", "ext")):
        return _melt_alien_objects(vars(obj))

    return obj

class SurgeBaseModel(BaseModel):
    """Topological Crucible"""
    
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        populate_by_name=True,
        extra='ignore'
    )

    @model_validator(mode='before')
    @classmethod
    def sanitize_namespaces(cls, data: Any) -> Any:
        """입력된 kwargs 딕셔너리 내부의 모든 외래 객체를 융해"""
        if isinstance(data, dict):
            return _melt_alien_objects(data)
        return data

    @classmethod
    def suture(cls: Type[T], **kwargs: Any) -> T:
        """@desc: model_construct를 캡슐화한 봉합"""
        melted_data = _melt_alien_objects(kwargs)
        instance = cls.model_construct(**melted_data)
        if hasattr(instance, "model_post_init"):
            instance.model_post_init(None)
        return instance