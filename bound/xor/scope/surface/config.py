# bound.xor.scope.surface.config
## @lineage: bound.scope.surface.config
## @lineage: gov.bridge.scope.surface.config
from abc import ABC, abstractmethod
import socket
from dataclasses import dataclass, field
from typing import Optional, Any, List
from watcher.plane.emitter import get_emitter

log = get_emitter("surface.config")

def get_free_port(starting_port: int, max_port: int = 8999) -> int:
    """충돌 방지를 위해 사용 가능한 빈 포트를 탐색합니다."""
    for port in range(starting_port, max_port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if sock.connect_ex(('0.0.0.0', port)) != 0:
                return port
    raise RuntimeError(f"No free ports available between {starting_port} and {max_port}.")

@dataclass
class SurfaceConfig:
    """실행 표면 설정을 위한 데이터 클래스"""
    use_was: bool = False
    use_dphi: bool = False
    use_thch: bool = False
    dphi_model: str = "local-gemma-3"
    host: str = "0.0.0.0"
    port: int = 8000
    timeout: int = 30
    show_logs: bool = True
    
    adapter: Optional[Any] = None
    callbacks: List[Any] = field(default_factory=list)
    trace: List[Any] = field(default_factory=list)
    ## TODO: 필요한 다른 기존 설정들(branch_idx 등)이 있다면 점진적으로 여기에 추가

class BaseSurface(ABC):
    @abstractmethod
    def up(self): pass

    @abstractmethod
    def down(self): pass

    @abstractmethod
    def get_engine(self): pass