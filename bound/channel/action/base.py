# bound.channel.action.base
## @lineage: bound.bridge.action.base
## @lineage: bound.client.action.base
## @lineage: anchor.router.action.base
## @lineage: bound.router.action.base
## @lineage: bound.channel.router.action.base
from typing import TYPE_CHECKING, Any, Optional, Union
import httpx

from anchor.base.config.resolver import config

if TYPE_CHECKING:
    from bound.transport.stream.wrapper import CustomStreamWrapper
    from anchor.surface.legacy.types.utils import ModelResponse, TextCompletionResponse

class BaseLLM:
    _client_session: Optional[httpx.Client] = None

    def process_response(
        self,
        model: str,
        response: httpx.Response,
        model_response: "ModelResponse",
        stream: bool,
        logging_obj: Any,
        optional_params: dict,
        api_key: str,
        data: Union[dict, str],
        messages: list,
        print_verbose,
        encoding,
    ) -> Union["ModelResponse", "CustomStreamWrapper"]:
        """
        Helper function to process the response across sync + async completion calls
        """
        return model_response

    def process_text_completion_response(
        self,
        model: str,
        response: httpx.Response,
        model_response: "TextCompletionResponse",
        stream: bool,
        logging_obj: Any,
        optional_params: dict,
        api_key: str,
        data: Union[dict, str],
        messages: list,
        print_verbose,
        encoding,
    ) -> Union["TextCompletionResponse", "CustomStreamWrapper"]:
        """
        Helper function to process the response across sync + async completion calls
        """
        return model_response

    def create_client_session(self):
        if config.client_session:
            _client_session = config.client_session
        else:
            _client_session = httpx.Client()
        return _client_session

    def create_aclient_session(self):
        if config.aclient_session:
            _aclient_session = config.aclient_session
        else:
            _aclient_session = httpx.AsyncClient()
        return _aclient_session

    def __exit__(self):
        if hasattr(self, "_client_session") and self._client_session is not None:
            self._client_session.close()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if hasattr(self, "_aclient_session"):
            await self._aclient_session.aclose()  # type: ignore

    def validate_environment(
        self, *args, **kwargs
    ) -> Optional[Any]:  # set up the environment required to run the model
        return None

    def completion(
        self, *args, **kwargs
    ) -> Any:  # logic for parsing in - calling - parsing out model completion calls
        return None

    def embedding(
        self, *args, **kwargs
    ) -> Any:  # logic for parsing in - calling - parsing out model embedding calls
        return None
