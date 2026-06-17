# arch.proto.event.next
import os
import shutil
import stat
import asyncio
import time
import threading
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Annotated
from phase.bind.resolver import resolve_identity
from datetime import UTC, datetime
from pydantic import Field

class ToposGenerator:
    def __init__(self, vertex_id: int = 1, manifold_id: int = 1):
        # 파라미터 제약 조건 (각 5비트이므로 0~31)
        self.worker_id = vertex_id & 0x1F
        self.datacenter_id = manifold_id & 0x1F
        self.sequence = 0
        self.epoch = 1767225600000 
        self.last_timestamp = -1
        self._lock = threading.Lock()

    def _timestamp(self) -> int:
        return int(time.time() * 1000)

    def generate(self) -> int:
        with self._lock:
            timestamp = self._timestamp()
            if timestamp < self.last_timestamp:
                offset = self.last_timestamp - timestamp
                if offset <= 5: # 5ms 이하의 미세한 시간 역행인 경우
                    time.sleep((offset + 1) / 1000.0) # 시간이 따라잡힐 때까지 잠깐 대기
                    timestamp = self._timestamp() # 시간 재측정
                else:
                    raise Exception(f"Clock moved backwards significantly! Refusing to generate id for {offset} milliseconds")

            if timestamp == self.last_timestamp:
                self.sequence = (self.sequence + 1) & 0xFFF # 12비트 마스크
                if self.sequence == 0:
                    # 동일 밀리초 내 시퀀스 소진 시 다음 밀리초까지 대기
                    while timestamp <= self.last_timestamp:
                        timestamp = self._timestamp()
            else:
                self.sequence = 0
            self.last_timestamp = timestamp

            # 비트 시프트 결합
            # (Timestamp - Epoch) << 22 | (DC) << 17 | (Worker) << 12 | Sequence
            return ((timestamp - self.epoch) << 22) | \
                   (self.datacenter_id << 17) | \
                   (self.worker_id << 12) | \
                   self.sequence

_manifold_id, _vertex_id = resolve_identity()
generator = ToposGenerator(vertex_id=_vertex_id, manifold_id=_manifold_id)

def next_id() -> str:
    """PsiEvent에 사용하기 좋게 문자열로 반환"""
    return str(generator.generate())

def parse_id(snowflake_id: str):
    """ID를 분석하여 생성 시점과 작업자 정보를 복원"""
    sid = int(snowflake_id)
    timestamp = (sid >> 22) + 1767225600000 # epoch 반영
    datacenter_id = (sid >> 17) & 0x1F
    worker_id = (sid >> 12) & 0x1F
    sequence = sid & 0xFFF
    return {
        "timestamp_ms": timestamp,
        "worker_info": f"{datacenter_id}:{worker_id}",
        "seq": sequence
    }

class PhaseIdGenerator:
    """
    @desc: 외부 기준점(Reference) 기반의 차분 위상 신호 생성기
    기존: self-memory 기반 (위험) -> 정정: reference-based operator (정합)
    """
    def __init__(self):
        self.prev_topo = 0
        self.prev_press = 0
        self.epoch = 0
        self._lock = threading.Lock()

    def generate(self, current_topo: int, current_press: int, 
                 ref_topo: Optional[int] = None, 
                 ref_press: Optional[int] = None, 
                 rupture: bool = False) -> int:
        """
        :param ref_topo: 외부(Lineage/Redis)에서 제공하는 위상 기준점
        :param ref_press: 외부(Signature/Context)에서 제공하는 압력 기준점
        """
        with self._lock:
            # 1. Epoch: 계보 단절(Discontinuity) 마커
            if rupture:
                self.epoch ^= 1
            
            # 2. 기준점 설정 (외부 참조 우선)
            base_t = ref_topo if ref_topo is not None else self.prev_topo
            base_p = ref_press if ref_press is not None else self.prev_press

            # 3. 차분 및 포화(Saturation) 연산
            # Overflow 왜곡을 방지하기 위해 min()으로 클리핑
            d_topo = current_topo - base_t
            topo_sign = 1 if d_topo >= 0 else 0
            topo_mag = min(abs(d_topo), 0x3FFF) # 14bit 포화
            
            d_press = current_press - base_p
            press_sign = 1 if d_press >= 0 else 0
            press_mag = min(abs(d_press), 0x7FFF) # 15bit 포화
            
            # 4. 상태 업데이트 (외부 기준이 없을 때만 내부 캐시 갱신)
            if ref_topo is None: self.prev_topo = current_topo
            if ref_press is None: self.prev_press = current_press
            
            # 5. 비트 패킹 (32bit)
            return (self.epoch << 31) | (topo_sign << 30) | (topo_mag << 16) | \
                   (press_sign << 15) | (press_mag)

phase_generator = PhaseIdGenerator()

def next_phase_id(topo: int, press: int, rupture: bool = False) -> int:
    """차분 위상 신호를 생성하여 반환"""
    return phase_generator.generate(topo, press, rupture)

def parse_phase_id(phase_id: int) -> Dict[str, Any]:
    """
    32비트 위상 신호를 분해하여 위상적 벡터(Topological Vector)를 복원합니다.
    [ Epoch(1) | TopoSign(1) | TopoMag(14) | PressSign(1) | PressMag(15) ]
    """
    # 1. 비트 필드 추출
    epoch = (phase_id >> 31) & 0x1
    t_sign_bit = (phase_id >> 30) & 0x1
    t_mag = (phase_id >> 16) & 0x3FFF
    p_sign_bit = (phase_id >> 15) & 0x1
    p_mag = phase_id & 0x7FFF

    # 2. 위상적 방향성 해석 (Topology)
    # + (1): Inversion (수렴/상위 전이), - (0): Dispersion (발산/하위 전이)
    t_direction = "INVERSION" if t_sign_bit == 1 else "DISPERSION"
    
    # 3. 압력 방향성 해석 (Pressure)
    # + (1): Tension (긴장/증가), - (0): Release (이완/감소)
    p_direction = "TENSION" if p_sign_bit == 1 else "RELEASE"

    # 4. 포화(Saturation) 감지
    # 최대치에 도달했다는 것은 현재 위상 해상도를 넘어선 'Scale Jump'의 징후임
    t_saturated = (t_mag == 0x3FFF)
    p_saturated = (p_mag == 0x7FFF)

    return {
        "epoch_rupture": bool(epoch),
        "topology": {
            "vector": t_direction,
            "delta": t_mag,
            "is_saturated": t_saturated # 상전이 임계점 도달 여부
        },
        "pressure": {
            "vector": p_direction,
            "delta": p_mag,
            "is_saturated": p_saturated # 스케일 점프 트리거 여부
        },
        "raw_hex": hex(phase_id)
    }

@dataclass
class LogEvent:
    """
    @event.contract: Telemetry counterpart to PsiEvent
    Identity(2) + Origin(3) + Content(3) + Metrics(3)
    """
    ## Identity (PsiEvent 호환)
    event_id: str = field(default_factory=next_id)
    phase_id: int = 0               # 신규 추가: 32bit ΔΨ 신호
    parent_id: Optional[str] = None  # 어떤 PsiEvent에 의해 발생한 로그인지 추적 가능
    
    ## Origin & Temporal (PsiEvent 호환)
    source_id: str = "unknown"       # 기존 source -> source_id 로 변경
    scope: str = "LOG"               # 기본 스코프
    tick: Optional[int] = None       # 시간축
    
    ## Content (Log 고유)
    level: str = "INFO"
    kind: str = "log"                # "log" or "summary" (carrier.kind 역할)
    message: str = ""
    
    ## Context (PsiEvent 호환 - 분산된 메타데이터 응집)
    context: Dict[str, Any] = field(default_factory=dict)
    
    ## Plane Metrics (BoundPlane 전용 제어 상태 - 동적 할당 방지)
    density: float = 0.0
    gain: float = 1.0
    fold_count: int = 1

def safe_rmtree(path: str | Path | None, description: str = "directory") -> bool:
    """Safely remove a directory tree, handling permission errors gracefully."""
    if not path or not os.path.exists(path):
        return True

    def handle_remove_readonly(func, path, _exc):
        """Error handler for removing read-only files."""
        if os.path.exists(path):
            try:
                os.chmod(path, stat.S_IWRITE)
                func(path)
            except (OSError, PermissionError) as e:
                logger.warning(f"Failed to remove read-only file {path}: {e}")

    try:
        shutil.rmtree(path, onerror=handle_remove_readonly)
        logger.debug(f"Successfully removed {description}: {path}")
        return True
    except (OSError, PermissionError) as e:
        logger.warning(
            f"Failed to remove {description} at {path}: {e}. "
            f"This may leave temporary files on disk but won't affect functionality."
        )
        return False
    except Exception as e:
        logger.error(f"Unexpected error removing {description} at {path}: {e}")
        return False


def utc_now():
    """Return the current time in UTC format (Since datetime.utcnow is deprecated)"""
    return datetime.now(UTC)

ToposId = Annotated[
    str, 
    Field(
        # default_factory=next_id, 
        description="Topological Snowflake ID (Replaces legacy UUID)"
    )
]