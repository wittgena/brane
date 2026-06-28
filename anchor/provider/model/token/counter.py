# anchor.provider.model.token.counter
## @lineage: anchor.channel.compat.switch.model.token.counter
## @lineage: anchor.channel.switch.model.token.counter
import base64
import io
import json
import struct
from typing import (
    Any,
    Callable,
    List,
    Literal,
    Mapping,
    Optional,
    Tuple,
    Union,
    cast,
)
import tiktoken

from anchor.channel.config.resolver import config
from anchor.channel.config.constants import (
    DEFAULT_IMAGE_HEIGHT,
    DEFAULT_IMAGE_TOKEN_COUNT,
    DEFAULT_IMAGE_WIDTH,
    MAX_IMAGE_URL_DOWNLOAD_SIZE_MB,
    MAX_LONG_SIDE_FOR_IMAGE_HIGH_RES,
    MAX_SHORT_SIDE_FOR_IMAGE_HIGH_RES,
    MAX_TILE_HEIGHT,
    MAX_TILE_WIDTH,
)
from anchor.provider.model.token.convert import get_default_encoding
from anchor.surface.model.anthropic import (
    AnthropicMessagesToolResultParam,
    AnthropicMessagesToolUseParam,
)
from anchor.surface.model.openai.types import (
    AllMessageValues,
    ChatCompletionNamedToolChoiceParam,
    ChatCompletionToolParam,
    OpenAIMessageContent,
)
from anchor.surface.model.types import SelectTokenizerResponse
from anchor.channel.compat.switch.params import Message
from anchor.channel.client.http import _get_httpx_client
from watcher.plane.emitter import get_emitter

# [NEW] 이전 단계에서 제안된 클래스 기반 안전한 HTTP 클라이언트 사용
from anchor.provider.model.token.url_utils import SafeHttpClient

log = get_emitter(__name__)

TokenCounterFunction = Callable[[str], int]


class TokenEvaluator:
    """
    모델, 토크나이저, 이미지 처리 설정 등의 상태를 보유하고
    메시지나 텍스트의 토큰을 계산하는 응집도 높은 평가(Evaluator) 엔진
    """

    def __init__(
        self,
        model: str = "",
        custom_tokenizer: Optional[Union[dict, SelectTokenizerResponse]] = None,
        use_default_image_token_count: bool = False,
        default_token_count: Optional[int] = None,
    ):
        self.original_model = model
        self.model = self._fix_model_name(model)
        self.custom_tokenizer = custom_tokenizer
        self.use_default_img_count = use_default_image_token_count
        self.default_token_count = default_token_count
        
        self.count_function = self._get_count_function()
        self._init_message_params()

    def _init_message_params(self):
        """모델에 따른 토큰 패딩(Padding) 규칙을 상태로 저장"""
        if self.model == "gpt-3.5-turbo-0301":
            self.tokens_per_message = 4
            self.tokens_per_name = -1
        elif self.model in config.open_ai_chat_completion_models or self.model in config.azure_llms:
            self.tokens_per_message = 3
            self.tokens_per_name = 1
        else:
            self.tokens_per_message = 3
            self.tokens_per_name = 1

    @staticmethod
    def _fix_model_name(model: str) -> str:
        """모델 이름을 정규화합니다."""
        if model in config.azure_llms:
            return model.replace("-35", "-3.5")
        elif model in config.open_ai_chat_completion_models:
            return model
        return "gpt-3.5-turbo"

    def _get_count_function(self) -> TokenCounterFunction:
        """현재 모델 상태에 맞는 토큰 계산 함수를 반환합니다."""
        from anchor.provider.model.token.tokenizer import _select_tokenizer
        
        if self.original_model or self.custom_tokenizer:
            tokenizer_json = self.custom_tokenizer or _select_tokenizer(self.original_model)
            
            if tokenizer_json["type"] == "huggingface_tokenizer":
                def count_tokens(text: str) -> int:
                    enc = tokenizer_json["tokenizer"].encode(text)
                    return len(enc.ids)
                return count_tokens
                
            elif tokenizer_json["type"] == "openai_tokenizer":
                try:
                    if "gpt-4o" in self.model:
                        encoding = get_default_encoding("o200k_base")
                    else:
                        encoding = tiktoken.encoding_for_model(self.model)
                except KeyError:
                    log.debug("Warning: model not found. Using cl100k_base encoding.")
                    encoding = get_default_encoding("cl100k_base")

                def count_tokens(text: str) -> int:
                    return len(encoding.encode(text, disallowed_special=()))
                return count_tokens
            else:
                raise ValueError("Unsupported tokenizer type")
        else:
            def count_tokens(text: str) -> int:
                encoding = get_default_encoding()
                return len(encoding.encode(text, disallowed_special=()))
            return count_tokens

    # ==========================================
    # Text & Message Counting Logic
    # ==========================================

    def count_text(self, text: Union[str, List[str]]) -> int:
        if isinstance(text, list):
            text_to_count = "".join(t for t in text if isinstance(t, str))
        else:
            text_to_count = text
        return self.count_function(text_to_count)

    def count_messages(
        self,
        messages: List[AllMessageValues],
        tools: Optional[List[ChatCompletionToolParam]] = None,
        tool_choice: Optional[ChatCompletionNamedToolChoiceParam] = None,
        count_response_tokens: bool = False,
    ) -> int:
        num_tokens = 0
        if not messages:
            return num_tokens

        for message in messages:
            num_tokens += self.tokens_per_message
            for key, value in message.items():
                if value is None:
                    continue
                
                if key == "tool_calls":
                    if isinstance(value, list):
                        for tool_call in value:
                            if "function" in tool_call:
                                func_args = tool_call["function"].get("arguments", [])
                                num_tokens += self.count_function(str(func_args))
                            else:
                                raise ValueError(f"Unsupported tool call {tool_call} must contain a function key")
                    else:
                        raise ValueError(f"Unsupported type {type(value)} for key tool_calls in message {message}")
                
                elif isinstance(value, str):
                    num_tokens += self.count_function(value)
                    if key == "name":
                        num_tokens += self.tokens_per_name
                
                elif key == "content" and isinstance(value, list):
                    num_tokens += self._count_content_list(value)
                
                elif key == "search_results" and isinstance(value, list):
                    search_results_text = self._extract_search_results_text(value)
                    if search_results_text:
                        num_tokens += self.count_function(search_results_text)

        if not count_response_tokens:
            includes_system = any(msg.get("role") == "system" for msg in messages)
            num_tokens += self._count_extra_tools(tools, tool_choice, includes_system)

        return num_tokens

    def _count_extra_tools(self, tools, tool_choice, includes_system_message: bool) -> int:
        num_tokens = 3 
        if tools:
            num_tokens += self.count_function(self._format_function_definitions(tools))
            num_tokens += 9
            
        if tools and includes_system_message:
            num_tokens -= 4
            
        if tool_choice == "none":
            num_tokens += 1
        elif isinstance(tool_choice, dict):
            num_tokens += 7
            num_tokens += self.count_function(str(tool_choice["function"]["name"]))

        return num_tokens

    def _count_content_list(self, content_list: OpenAIMessageContent) -> int:
        try:
            num_tokens = 0
            for c in content_list:
                if isinstance(c, str):
                    num_tokens += self.count_function(c)
                elif c["type"] == "text":
                    num_tokens += self.count_function(str(c.get("text", "")))
                elif c["type"] == "image_url":
                    num_tokens += self._count_image_tokens(c.get("image_url"))
                elif c["type"] in ("tool_use", "tool_result"):
                    num_tokens += self._count_anthropic_content(c)
                elif c["type"] == "thinking":
                    thinking_text = str(c.get("thinking", ""))
                    if thinking_text:
                        num_tokens += self.count_function(thinking_text)
                else:
                    content_type = c.get("type", type(c).__name__) if isinstance(c, dict) else type(c).__name__
                    raise ValueError(f"Invalid content item type: {content_type}.")
            return num_tokens
        except Exception as e:
            if self.default_token_count is not None:
                return self.default_token_count
            raise ValueError(f"Error getting number of tokens from content list: {e}")

    def _count_anthropic_content(self, content: Mapping[str, Any]) -> int:
        typeddict_cls = self._validate_anthropic_content(content)
        type_hints = getattr(typeddict_cls, "__annotations__", {})
        tokens = 0
        skip_fields = {"type", "id", "tool_use_id", "cache_control", "is_error"}

        for field_name in type_hints.keys():
            if field_name in skip_fields:
                continue
            field_value = content.get(field_name)
            if field_value is None:
                continue
                
            try:
                if isinstance(field_value, str):
                    tokens += self.count_function(field_value)
                elif isinstance(field_value, list):
                    tokens += self._count_content_list(field_value)
                elif isinstance(field_value, dict):
                    tokens += self.count_function(str(field_value))
            except Exception as e:
                if self.default_token_count is not None:
                    return self.default_token_count
                raise ValueError(f"Error counting field '{field_name}': {e}")
        return tokens

    @staticmethod
    def _validate_anthropic_content(content: Mapping[str, Any]) -> type:
        content_type = content.get("type")
        if not content_type:
            raise ValueError("Anthropic content missing required field: 'type'")

        mapping = {
            "tool_use": AnthropicMessagesToolUseParam,
            "tool_result": AnthropicMessagesToolResultParam,
        }

        expected_cls = mapping.get(content_type)
        if expected_cls is None:
            raise ValueError(f"Unknown Anthropic content type: '{content_type}'")

        missing = [k for k in getattr(expected_cls, "__required_keys__", set()) if k not in content]
        if missing:
            raise ValueError(f"Missing required fields in {content_type} block: {', '.join(missing)}")
        return expected_cls

    @staticmethod
    def _extract_search_results_text(search_results: object) -> str:
        if not isinstance(search_results, list):
            return ""
        texts = ""
        for result in search_results:
            if not isinstance(result, dict):
                continue
            for key in ("source", "title"):
                value = result.get(key)
                if isinstance(value, str):
                    texts += value
            content = result.get("content")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        text = block.get("text")
                        if isinstance(text, str):
                            texts += text
            
            citations = result.get("citations")
            if citations is not None:
                # [FIX] json 모듈이 임포트되어 이제 안전하게 실행됨
                texts += json.dumps(citations, separators=(",", ":"))
        return texts

    # ==========================================
    # Tool Formatting Logic
    # ==========================================

    @classmethod
    def _format_function_definitions(cls, tools) -> str:
        lines = ["namespace functions {", ""]
        for tool in tools:
            if not isinstance(tool, dict):
                continue
            function = tool.get("function")
            if not isinstance(function, dict):
                params = tool.get("input_schema") or tool.get("parameters") or {}
                if not isinstance(params, dict):
                    params = {}
                function = {
                    "name": tool.get("name"),
                    "description": tool.get("description"),
                    "parameters": params,
                }
                
            function_name = function.get("name")
            if not function_name:
                continue
                
            if function_description := function.get("description"):
                lines.append(f"// {function_description}")
                
            parameters = function.get("parameters") or {}
            if not isinstance(parameters, dict):
                parameters = {}
                
            properties = parameters.get("properties")
            if properties and properties.keys():
                lines.append(f"type {function_name} = (_: {{")
                lines.append(cls._format_object_parameters(parameters, 0))
                lines.append("}) => any;")
            else:
                lines.append(f"type {function_name} = () => any;")
            lines.append("")
            
        lines.append("} // namespace functions")
        return "\n".join(lines)

    @classmethod
    def _format_object_parameters(cls, parameters, indent) -> str:
        properties = parameters.get("properties")
        if not properties:
            return ""
        required_params = parameters.get("required", [])
        lines = []
        for key, props in properties.items():
            description = props.get("description")
            if description:
                lines.append(f"// {description}")
            question = "" if required_params and key in required_params else "?"
            lines.append(f"{key}{question}: {cls._format_type(props, indent)},")
        return "\n".join([" " * max(0, indent) + line for line in lines])

    @classmethod
    def _format_type(cls, props, indent) -> str:
        obj_type = props.get("type")
        if obj_type == "string":
            return " | ".join([f'"{item}"' for item in props["enum"]]) if "enum" in props else "string"
        elif obj_type == "array":
            return f"{cls._format_type(props['items'], indent)}[]"
        elif obj_type == "object":
            return f"{{\n{cls._format_object_parameters(props, indent + 2)}\n}}"
        elif obj_type in ["integer", "number"]:
            return " | ".join([f'"{item}"' for item in props["enum"]]) if "enum" in props else "number"
        elif obj_type == "boolean":
            return "boolean"
        elif obj_type == "null":
            return "null"
        return "any"

    # ==========================================
    # Image Counting Logic
    # ==========================================

    def _count_image_tokens(self, image_url: Any) -> int:
        if isinstance(image_url, dict):
            detail = image_url.get("detail", "auto")
            if detail not in ["low", "high", "auto"]:
                raise ValueError(f"Invalid detail value: {detail}.")
            url = image_url.get("url")
            if not url:
                raise ValueError("Missing required key 'url' in image_url dict.")
                
            return self._calculate_img_tokens(data=url, mode=detail)
            
        elif isinstance(image_url, str):
            if not image_url.strip():
                raise ValueError("Empty image_url string is not valid.")
            return self._calculate_img_tokens(data=image_url, mode="auto")
        else:
            raise ValueError("Invalid image_url type. Expected str or dict with 'url' field.")

    def _calculate_img_tokens(
        self,
        data,
        mode: Literal["low", "high", "auto"] = "auto",
        base_tokens: int = 85,
    ) -> int:
        if self.use_default_img_count:
            log.debug(f"Using default image token count: {DEFAULT_IMAGE_TOKEN_COUNT}")
            return DEFAULT_IMAGE_TOKEN_COUNT
            
        if mode in ("low", "auto"):
            return base_tokens
            
        width, height = self._get_image_dimensions(data)
        resized_width, resized_height = self._resize_image_high_res(width, height)
        tiles_needed = self._calculate_tiles_needed(resized_width, resized_height)
        
        return base_tokens + ((base_tokens * 2) * tiles_needed)

    @staticmethod
    def _get_image_dimensions(data: str) -> Tuple[int, int]:
        img_data = None
        if data.startswith(("http://", "https://")):
            try:
                client = _get_httpx_client()
                safe_client = SafeHttpClient(client)  # [NEW] 의존성 주입된 객체 사용
                response = safe_client.get(data)
                max_bytes = int(MAX_IMAGE_URL_DOWNLOAD_SIZE_MB * 1024 * 1024)
                
                content_length = response.headers.get("Content-Length")
                if content_length is None or int(content_length) <= max_bytes:
                    body = response.read()
                    if len(body) <= max_bytes:
                        img_data = body
            except Exception as e:
                # [FIX] 예외가 무음 처리(Swallow)되지 않도록 로깅 추가
                log.warning(f"Failed to fetch image dimensions from URL: {e}")

        if img_data is None:
            try:
                _header, encoded = data.split(",", 1)
                img_data = base64.b64decode(encoded)
            except Exception as e:
                log.warning(f"Failed to decode base64 image data: {e}")
                return DEFAULT_IMAGE_WIDTH, DEFAULT_IMAGE_HEIGHT

        img_type = TokenEvaluator._get_image_type(img_data)

        try:
            if img_type == "png":
                w, h = struct.unpack(">LL", img_data[16:24])
                return w, h
            elif img_type == "gif":
                w, h = struct.unpack("<HH", img_data[6:10])
                return w, h
            elif img_type == "jpeg":
                with io.BytesIO(img_data) as fhandle:
                    fhandle.seek(0)
                    size = 2
                    ftype = 0
                    while not 0xC0 <= ftype <= 0xCF or ftype in (0xC4, 0xC8, 0xCC):
                        fhandle.seek(size, 1)
                        byte = fhandle.read(1)
                        while ord(byte) == 0xFF:
                            byte = fhandle.read(1)
                        ftype = ord(byte)
                        size = struct.unpack(">H", fhandle.read(2))[0] - 2
                    fhandle.seek(1, 1)
                    h, w = struct.unpack(">HH", fhandle.read(4))
                return w, h
            elif img_type == "webp":
                if img_data[12:16] == b"VP8X":
                    w = struct.unpack("<I", img_data[24:27] + b"\x00")[0] + 1
                    h = struct.unpack("<I", img_data[27:30] + b"\x00")[0] + 1
                    return w, h
                elif img_data[12:16] == b"VP8 ":
                    w = struct.unpack("<H", img_data[26:28])[0] & 0x3FFF
                    h = struct.unpack("<H", img_data[28:30])[0] & 0x3FFF
                    return w, h
                elif img_data[12:16] == b"VP8L":
                    bits = struct.unpack("<I", img_data[21:25])[0]
                    w = (bits & 0x3FFF) + 1
                    h = ((bits >> 14) & 0x3FFF) + 1
                    return w, h
        except struct.error:
            pass

        return DEFAULT_IMAGE_WIDTH, DEFAULT_IMAGE_HEIGHT

    @staticmethod
    def _get_image_type(image_data: bytes) -> Union[str, None]:
        if image_data[0:8] == b"\x89\x50\x4e\x47\x0d\x0a\x1a\x0a":
            return "png"
        if image_data[0:4] == b"GIF8" and image_data[5:6] == b"a":
            return "gif"
        if image_data[0:3] == b"\xff\xd8\xff":
            return "jpeg"
        if image_data[4:8] == b"ftyp":
            return "heic"
        if image_data[0:4] == b"RIFF" and image_data[8:12] == b"WEBP":
            return "webp"
        return None

    @staticmethod
    def _resize_image_high_res(width: int, height: int) -> Tuple[int, int]:
        max_short_side = MAX_SHORT_SIDE_FOR_IMAGE_HIGH_RES
        max_long_side = MAX_LONG_SIDE_FOR_IMAGE_HIGH_RES

        if width <= max_short_side and height <= max_short_side:
            return width, height

        aspect_ratio = max(width, height) / min(width, height)

        if width <= height:
            resized_width = max_short_side
            resized_height = int(resized_width * aspect_ratio)
            if resized_height > max_long_side:
                resized_height = max_long_side
                resized_width = int(resized_height / aspect_ratio)
        else:
            resized_height = max_short_side
            resized_width = int(resized_height * aspect_ratio)
            if resized_width > max_long_side:
                resized_width = max_long_side
                resized_height = int(resized_width / aspect_ratio)

        return resized_width, resized_height

    @staticmethod
    def _calculate_tiles_needed(
        resized_width,
        resized_height,
        tile_width=MAX_TILE_WIDTH,
        tile_height=MAX_TILE_HEIGHT,
    ) -> int:
        tiles_across = (resized_width + tile_width - 1) // tile_width
        tiles_down = (resized_height + tile_height - 1) // tile_height
        return tiles_across * tiles_down


# ==========================================
# External Export Facades (시그니처 유지)
# ==========================================

def token_counter(
    model="",
    custom_tokenizer: Optional[Union[dict, SelectTokenizerResponse]] = None,
    text: Optional[Union[str, List[str]]] = None,
    messages: Optional[List[Union[AllMessageValues, Message]]] = None,
    count_response_tokens: Optional[bool] = False,
    tools: Optional[List[ChatCompletionToolParam]] = None,
    tool_choice: Optional[ChatCompletionNamedToolChoiceParam] = None,
    use_default_image_token_count: Optional[bool] = False,
    default_token_count: Optional[int] = None,
) -> int:
    """
    내부적으로 TokenEvaluator를 생성하여 토큰 수를 계산합니다. 
    (기존 서명 완벽 유지)
    """
    from anchor.provider.model.token.convert import convert_list_message_to_dict
    
    log.debug(f"messages in token_counter: {messages}, text in token_counter: {text}")

    if text is not None and messages is not None:
        raise ValueError("text and messages cannot both be set")

    evaluator = TokenEvaluator(
        model=model,
        custom_tokenizer=custom_tokenizer,
        use_default_image_token_count=bool(use_default_image_token_count),
        default_token_count=default_token_count,
    )

    if text is not None:
        if tools or tool_choice:
            raise ValueError("tools or tool_choice cannot be set if using text")
        return evaluator.count_text(text)

    elif messages is not None:
        new_messages = cast(List[AllMessageValues], convert_list_message_to_dict(messages))
        return evaluator.count_messages(
            messages=new_messages,
            tools=tools,
            tool_choice=tool_choice,
            count_response_tokens=bool(count_response_tokens),
        )
    else:
        raise ValueError("Either text or messages must be provided")


def get_modified_max_tokens(
    model: str,
    base_model: str,
    messages: Optional[List[AllMessageValues]],
    user_max_tokens: Optional[int],
    buffer_perc: Optional[float],
    buffer_num: Optional[float],
) -> Optional[int]:
    """
    기존 로직과 서명을 그대로 유지하며, 내부적으로 리팩토링된 token_counter를 활용합니다.
    """
    try:
        if user_max_tokens is None:
            return None

        _model_info = config.get_model_info(model=model)
        max_output_tokens = config.get_max_tokens(model=base_model)

        if max_output_tokens is None:
            return user_max_tokens

        input_tokens = token_counter(model=base_model, messages=messages)

        buffer_perc = buffer_perc if buffer_perc is not None else 0.1
        buffer_num = buffer_num if buffer_num is not None else 10.0
        token_buffer = max(buffer_perc * input_tokens, buffer_num)

        input_tokens += int(token_buffer)
        log.debug(f"max_output_tokens: {max_output_tokens}, user_max_tokens: {user_max_tokens}")

        if _model_info["max_input_tokens"] == max_output_tokens:
            log.debug(f"input_tokens: {input_tokens}, max_output_tokens: {max_output_tokens}")
            if input_tokens > max_output_tokens:
                pass
            elif user_max_tokens + input_tokens > max_output_tokens:
                log.debug(
                    f"MODIFYING MAX TOKENS - user_max_tokens={user_max_tokens}, "
                    f"input_tokens={input_tokens}, max_output_tokens={max_output_tokens}"
                )
                user_max_tokens = int(max_output_tokens - input_tokens)
        elif user_max_tokens > max_output_tokens:
            user_max_tokens = max_output_tokens

        log.debug(f"[token.counter] get_modified_max_tokens() - user_max_tokens: {user_max_tokens}")
        return user_max_tokens

    except Exception as e:
        log.debug(
            f"[token.counter.py] get_modified_max_tokens() - Error while checking max token limit: {e}\n"
            f"model={model}, base_model={base_model}"
        )
        return user_max_tokens