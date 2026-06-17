# arch.proto.wrapper.code
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol, runtime_checkable

PRIMITIVE_TYPES = (str, int, float, bool, list, dict, tuple, type(None))

class SandboxError(RuntimeError):
    """샌드박스 환경 예외의 기저 클래스"""
    pass

class ExecutionError(SandboxError):
    """
    실행 위상 오류 (Execution Error)
    - 주입된 코드의 런타임 오류 (NameError, TypeError 등)
    - 주입된 Callable 객체의 실행 실패
    """
    pass

class ProtocolError(SandboxError):
    """
    인프라/통신 위상 오류 (Protocol Error)
    - 호스트와 샌드박스 간 IPC 붕괴, 잘못된 JSON-RPC 포맷
    - 프로세스 크래시 등 샌드박스 재생성이 필요한 상태
    """
    pass


# ==========================================
# Data Flow: 불변의 결과 컨테이너
# ==========================================
@dataclass(frozen=True)
class ExecutionResult:
    """
    코드 실행의 순수한 변환 결과.
    이 데이터의 재사용/폐기 여부는 현재 위상에서 결정되지 않음.
    frozen=True를 통해 반환 이후의 사이드 이펙트를 원천 차단.
    """
    success: bool
    output: Any | None = None
    error: ExecutionError | None = None


# ==========================================
# Interface: 상태 없는(Stateless) 실행기 규약
# ==========================================
@runtime_checkable
class CodeInterpreter(Protocol):
    """
    사이드 이펙트가 없는 순수 실행 환경 프로토콜.
    상태(callables, variables)는 인스턴스에 저장되지 않고, 오직 실행 시점에만 주입됨.
    """

    def start(self) -> None:
        """실행 환경의 인프라 초기화"""
        ...

    def execute(
        self,
        code: str,
        variables: Mapping[str, Any] | None = None,
        callables: Mapping[str, Callable[..., Any]] | None = None,
    ) -> ExecutionResult:
        """
        주입된 데이터(variables)와 함수(callables)를 컨텍스트로 삼아 코드를 실행.
        
        - Mutable한 dict 대신 Mapping을 사용하여 인터페이스 레벨에서 조작(Side-effect) 방지.
        - 결과는 구조화된 ExecutionResult로 반환.
        """
        ...

    def shutdown(self) -> None:
        """실행 환경의 자원 해제"""
        ...