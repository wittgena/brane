# arch.proto.wrapper.jsonrpc
import json
from typing import Any, Mapping

class JsonRpcErrorCode:
    """
    JSON-RPC 2.0 표준 및 애플리케이션 에러 코드.
    매직 넘버를 배제하고 위상적으로 오류 타입을 분류합니다.
    """
    # Standard JSON-RPC 2.0 Errors
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603

    # Application Specific Errors (Sandbox)
    SYNTAX_ERROR = -32000
    NAME_ERROR = -32001
    TYPE_ERROR = -32002
    VALUE_ERROR = -32003
    ATTRIBUTE_ERROR = -32004
    INDEX_ERROR = -32005
    KEY_ERROR = -32006
    RUNTIME_ERROR = -32007
    UNKNOWN = -32099

    @classmethod
    def from_exception_type(cls, error_type: str) -> int:
        """예외 타입 문자열을 기반으로 적절한 RPC 에러 코드를 매핑합니다."""
        attr_name = error_type.replace("Error", "_ERROR").upper()
        return getattr(cls, attr_name, cls.UNKNOWN)


class JsonRpcMessage:
    """
    JSON-RPC 2.0 페이로드를 생성하는 순수(Stateless) 빌더 클래스.
    상태를 가지지 않으며(Side-effect free), 오직 규격에 맞는 직렬화된 문자열만 반환합니다.
    """
    VERSION = "2.0"

    @classmethod
    def request(cls, method: str, params: Mapping[str, Any], msg_id: int | str) -> str:
        """응답을 기대하는 요청(Request) 메시지를 생성합니다."""
        return json.dumps({
            "jsonrpc": cls.VERSION,
            "method": method,
            "params": params,
            "id": msg_id
        })

    @classmethod
    def notification(cls, method: str, params: Mapping[str, Any] | None = None) -> str:
        """응답을 기대하지 않는 단방향 알림(Notification) 메시지를 생성합니다."""
        msg: dict[str, Any] = {
            "jsonrpc": cls.VERSION, 
            "method": method
        }
        if params:
            msg["params"] = params
        return json.dumps(msg)

    @classmethod
    def result(cls, result: Any, msg_id: int | str) -> str:
        """성공적인 실행 결과(Result) 메시지를 생성합니다."""
        return json.dumps({
            "jsonrpc": cls.VERSION,
            "result": result,
            "id": msg_id
        })

    @classmethod
    def error(
        cls, 
        code: int, 
        message: str, 
        msg_id: int | str | None, 
        data: Mapping[str, Any] | None = None
    ) -> str:
        """실패한 실행의 에러(Error) 메시지를 생성합니다."""
        err: dict[str, Any] = {
            "code": code, 
            "message": message
        }
        if data:
            err["data"] = data
        return json.dumps({
            "jsonrpc": cls.VERSION,
            "error": err,
            "id": msg_id
        })