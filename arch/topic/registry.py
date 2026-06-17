# arch.topic.registry
## @lineage: arch.model.topic.registry
## @lineage: arch.project.topic.registry
## @lineage: xphi.code.topic.registry
## @lineage: topos.arch.code.topic.registry
## @lineage: arch.model.code.topic.registry
import json
from typing import Any, Callable, Dict, Optional, Union, List, Any
from pydantic import BaseModel, Field, ConfigDict

class CoreModuleInfo(BaseModel):
    """Phase Space 내의 핵심 모듈 정보"""
    path: str = Field(..., description="모듈의 파일 시스템 경로")
    density: float = Field(..., description="해당 Phase 내의 위상적 밀도(확률)")

class ToposSpace(BaseModel):
    """위상적으로 클러스터링된 하위 시스템(Subsystem) 정보"""
    topos_markers: List[str] = Field(..., description="해당 공간을 식별하는 주요 심볼들 (Boundary 후보)")
    core_modules: List[CoreModuleInfo] = Field(..., description="해당 공간의 중추 역할을 하는 모듈들")

class TopicMetadata(BaseModel):
    """저장소 전역 위상 메타데이터"""
    repository: str
    analyzed_modules: int
    global_interfaces: List[str] = Field(..., description="시스템 버스(Bus) 역할을 하는 전역 인터페이스 리스트")
    local_variants: Dict[str, List[str]] = Field(..., description="각 Phase 고유의 변이 심볼들")

class TopicMap(BaseModel):
    """Topic Space Map"""
    metadata: TopicMetadata
    spaces: Dict[str, ToposSpace]
    module_alignment: Dict[str, Dict[str, Any]] = Field(..., description="모듈별 Phase 소속 정보")

    @classmethod
    def load_from_json(cls, file_path: str) -> "TopicMap":
        """JSON 파일을 읽어 TopicMap 객체로 결속(Bound)합니다."""
        with open(file_path, "r", encoding="utf-8") as f:
            import json
            return cls.model_validate(json.load(f))

class TopicSchema(BaseModel):
    """Φ_canonical: 경계에서 수집된 파편을 실체(Bound)로 응집한 표준 위상 스키마"""
    model_config = ConfigDict(arbitrary_types_allowed=True) # Callable 허용
    name: str = Field(..., description="객체 또는 도구의 식별자")
    module_origin: Optional[str] = Field(None, description="원본 모듈 경로의 위치)")
    
    ## [Boundary Echoes] 경계면 현상 데이터
    status: str = Field("Unresolved", description="발현 상태: Signature_Captured | Deep_Boundary_Mapped")
    traces: Dict[str, Any] = Field(default_factory=dict, description="Tracer가 수집한 원시 반향 데이터")
    
    ## [Bound Structure] 실체적 결속 데이터
    description: Optional[str] = Field(None, description="추론된 도구의 목적")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="구조적 요구사항 (JSON Schema)")
    executable: Optional[Callable] = Field(None, exclude=True, description="실제 실행 가능한 결속체")

class TopicRegistry:
    """Bound Registry: 파편화된 가설들을 하나의 위상 지도(Map)로 결속하는 저장소"""
    def __init__(self):
        self._hypotheses: Dict[str, TopicSchema] = {}

    def assimilate(self, module_name: str, target_name: str, echoes: Dict[str, Any]):
        """Binder에서 전달된 Echoes를 ExtSchema로 변환하여 결속(Bound)"""
        key = f"{module_name}::{target_name}"
        
        ## Echoes의 깊이에 따른 상태 결정
        state = "Signature_Captured"
        if echoes.get("behavioral_map"):
            state = "Deep_Boundary_Mapped"

        ## 파편을 표준 스키마로 응집
        schema = TopicSchema(
            name=target_name,
            module_origin=module_name,
            status=state,
            traces=echoes,
            parameters={"raw_sig": echoes.get("signature")} 
        )
        self._hypotheses[key] = schema

    def get_hypothesis(self, key: str) -> Optional[TopicSchema]:
        return self._hypotheses.get(key)

    def dump(self) -> str:
        """가설의 전질(Whole)을 JSON으로 출력 (실행체 제외)"""
        return json.dumps(
            {k: v.model_dump() for k, v in self._hypotheses.items()}, 
            indent=2, ensure_ascii=False
        )