# xphi.scope.surface.config
from abc import ABC, abstractmethod
import socket
from dataclasses import dataclass, field
from typing import Optional, Any, List
from watcher.plane.emitter import get_emitter

log = get_emitter("surface.config")

def get_free_port(starting_port: int, max_port: int = 8999) -> int:
    """운영체제 바인딩 검증 방식을 사용하여 충돌 가능성이 전혀 없는 빈 포트를 정확히 탐색"""
    for port in range(starting_port, max_port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(('127.0.0.1', port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free ports available between {starting_port} and {max_port}.")

@dataclass
class SurfaceConfig:
    """실행 표면 설정을 위한 고도화된 데이터 클래스"""
    use_proxy: bool = False
    use_dphi: bool = False
    use_thch: bool = False
    dphi_model: str = "local-gemma-3"
    host: str = "0.0.0.0"
    port: int = 8000
    timeout: int = 30
    show_logs: bool = True
    
    server_url: str = "http://localhost:8000"
    workspace_ref: Optional[str] = None
    session_api_key: Optional[str] = None
    adapter: Optional[Any] = None
    callbacks: List[Any] = field(default_factory=list)
    trace: List[Any] = field(default_factory=list)

class BaseSurface(ABC):
    @abstractmethod
    def up(self) -> None: pass

    @abstractmethod
    def down(self) -> None: pass

    @abstractmethod
    def get_engine(self) -> Any: pass