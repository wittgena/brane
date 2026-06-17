# phase.runtime.cli.task
## @lineage: phase.executor.event.task
## @lineage: arch.executor.event.task
import time
import uuid
import json
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional

@dataclass
class TaskSummaryEvent:
    """
    이벤트 버스(PsiCarrier)에 탑재될 초경량 요약 모델.
    수신자는 detail_key를 통해 Redis에서 상세 데이터를 조회할 수 있습니다.
    """
    task_id: str
    command: str          # 실행 파일/명령어 명 (ex: "meta.anchor.modeler")
    status: str           # "SUCCESS", "FAILED", "PARTIAL"
    summary: str          # 간단한 한 줄 요약
    detail_key: str       # Redis에서 상세 데이터를 찾기 위한 키
    details: dict[str, Any]

    def to_json(self) -> str:
        """객체를 JSON 문자열로 변환 (Surface 투영용)"""
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, json_str: str):
        """JSON 문자열을 객체로 복원 (Capture용)"""
        data = json.loads(json_str)
        return cls(**data)


@dataclass
class TaskDetailRecord:
    """
    Redis에 저장될 상세 데이터 모델.
    표준 규격과 비표준 규격(details)을 엄격히 분리합니다.
    """
    task_id: str
    command: str
    status: str
    
    artifacts: Dict[str, Any] = field(default_factory=lambda: {
        "base_dir": "",
        "files": []
    })

    metrics: Dict[str, Any] = field(default_factory=lambda: {
        "elapsed_ms": 0,
        "scanned_count": 0,
        "processed_count": 0
    })

    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    
    def to_json(self) -> str:
        """객체를 JSON 문자열로 변환 (Surface 투영용)"""
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, json_str: str):
        """JSON 문자열을 객체로 복원 (Capture용)"""
        data = json.loads(json_str)
        return cls(**data)