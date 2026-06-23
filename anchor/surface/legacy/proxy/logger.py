# anchor.surface.legacy.proxy.logger
from datetime import datetime
from typing import Any, Dict, Optional, Tuple
import traceback

from litellm.proxy.proxy_server import proxy_logging_obj

from anchor.surface.legacy.proxy.rule import Rules
from anchor.base.config.constants import MAXIMUM_TRACEBACK_LINES_TO_LOG
from bound.channel.wrapper import function_setup
from xphi.scope.plane.delegator import Logging as LiteLLMLoggingObj
from watcher.plane.emitter import get_emitter

log = get_emitter("proxy.logger")

class LegacyLogManager:
    """litellm의 복잡한 로깅, 트레이싱, 훅(Hook) 호출을 캡슐화한 어댑터"""
    @staticmethod
    async def log_pre_call(
        tool_name: str, 
        logging_request_data: Dict[str, Any], 
        logging_input: Any, 
        start_time: datetime
    ) -> Tuple[Optional[LiteLLMLoggingObj], Dict[str, Any]]:
        litellm_logging_obj = None
        rules_obj = Rules()
        
        try:
            litellm_logging_obj, _ = function_setup(
                original_function="call_mcp_tool",
                rules_obj=rules_obj,
                start_time=start_time,
                **logging_request_data,
            )
        except Exception as logging_error:
            log.debug(f"Failed to init logging for {tool_name}: {logging_error}")
            
        logging_request_data["litellm_logging_obj"] = litellm_logging_obj
        
        if litellm_logging_obj:
            try:
                litellm_logging_obj.pre_call(input=logging_input, api_key="")
            except Exception:
                log.exception("Failed to run pre_call for MCP tool logging")
                
        return litellm_logging_obj, logging_request_data

    @staticmethod
    async def log_post_call_success(
        litellm_logging_obj: Optional[LiteLLMLoggingObj], 
        result: Any, 
        start_time: datetime,
        tool_name: str
    ) -> None:
        """툴 실행 성공 시의 post_call 및 훅 로직 묶음"""
        if not litellm_logging_obj:
            return
            
        try:
            litellm_logging_obj.post_call(original_response=result)
            end_time = datetime.now()
            await litellm_logging_obj.async_post_mcp_tool_call_hook(
                kwargs=litellm_logging_obj.model_call_details,
                response_obj=result,
                start_time=start_time,
                end_time=end_time,
            )
            await litellm_logging_obj.async_success_handler(
                result=result,
                start_time=start_time,
                end_time=end_time,
            )
        except Exception:
            log.exception(f"Failed to log MCP tool call success for {tool_name}")

    @staticmethod
    async def log_failure(
        user_api_key_auth: Any,
        request_data: Dict[str, Any],
        error: Exception,
    ) -> None:
        """기존 _log_mcp_tool_failure 메서드 대체"""
        if proxy_logging_obj is None or user_api_key_auth is None:
            return

        try:
            traceback_str = traceback.format_exc(limit=MAXIMUM_TRACEBACK_LINES_TO_LOG)
            await proxy_logging_obj.post_call_failure_hook(
                request_data=request_data,
                original_exception=error,
                user_api_key_dict=user_api_key_auth,
                route="/responses/mcp/call_tool",
                traceback_str=traceback_str,
            )
        except Exception:
            log.exception("Failed to log MCP tool call failure")