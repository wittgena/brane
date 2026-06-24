# anchor.model.token.tokenizer
## @lineage: anchor.router.model.token.tokenizer
## @lineage: bound.router.model.token.tokenizer
## @lineage: bound.channel.model.token.tokenizer
## @lineage: channel.model.token.tokenizer
## @lineage: bound.token.tokenizer
from functools import lru_cache, wraps
from typing import Dict, List, Optional, Type
from tokenizers import Tokenizer
from anchor.surface.legacy.llm.types.utils import CustomHuggingfaceTokenizer, SelectTokenizerResponse
from anchor.model.token.encoding import get_default_encoding
from anchor.surface.config.constants import DEFAULT_MAX_LRU_CACHE_SIZE
from watcher.plane.emitter import get_emitter

log = get_emitter("token.tokenizer")

def encode(model="", text="", custom_tokenizer: Optional[dict] = None):
    tokenizer_json = custom_tokenizer or _select_tokenizer(model=model)
    if isinstance(tokenizer_json["tokenizer"], Encoding):
        enc = tokenizer_json["tokenizer"].encode(text, disallowed_special=())
    else:
        enc = tokenizer_json["tokenizer"].encode(text)
    if hasattr(enc, "ids"):
        return enc.ids  # type: ignore
    return enc

def decode(
    model="",
    tokens: List[int] = [],
    custom_tokenizer: Optional[dict] = None,
    skip_special_tokens: bool = True,
):
    tokenizer_json = custom_tokenizer or _select_tokenizer(model=model)
    if tokenizer_json["type"] == "huggingface_tokenizer":
        if skip_special_tokens:
            tokens = _strip_huggingface_special_token_ids(
                tokenizer_json["tokenizer"], tokens
            )
        dec = tokenizer_json["tokenizer"].decode(
            tokens, skip_special_tokens=skip_special_tokens
        )
        return dec
    dec = tokenizer_json["tokenizer"].decode(tokens)
    return dec

def _select_tokenizer(model: str, custom_tokenizer: Optional[CustomHuggingfaceTokenizer] = None):
    if custom_tokenizer is not None:
        _tokenizer = create_pretrained_tokenizer(
            identifier=custom_tokenizer["identifier"],
            revision=custom_tokenizer["revision"],
            auth_token=custom_tokenizer["auth_token"],
        )
        return _tokenizer
    return _select_tokenizer_helper(model=model)

@lru_cache(maxsize=DEFAULT_MAX_LRU_CACHE_SIZE)
def _select_tokenizer_helper(model: str) -> SelectTokenizerResponse:
    if litellm.disable_hf_tokenizer_download is True:
        return _return_openai_tokenizer(model)

    try:
        result = _return_huggingface_tokenizer(model)
        if result is not None:
            return result
    except Exception as e:
        log.debug(f"Error selecting tokenizer: {e}")

def _return_openai_tokenizer(model: str) -> SelectTokenizerResponse:
    return {"type": "openai_tokenizer", "tokenizer": get_default_encoding()}
    return _return_openai_tokenizer(model)

def _return_huggingface_tokenizer(model: str) -> Optional[SelectTokenizerResponse]:
    # anthropic
    if model in litellm.anthropic_models and "claude-3" not in model:
        claude_tokenizer = Tokenizer.from_str(claude_json_str)
        return {"type": "huggingface_tokenizer", "tokenizer": claude_tokenizer}
    # llama2
    elif "llama-2" in model.lower():
        tokenizer = Tokenizer.from_pretrained("hf-internal-testing/llama-tokenizer")
        return {"type": "huggingface_tokenizer", "tokenizer": tokenizer}
    # llama3
    elif "llama-3" in model.lower():
        tokenizer = Tokenizer.from_pretrained("Xenova/llama-3-tokenizer")
        return {"type": "huggingface_tokenizer", "tokenizer": tokenizer}
    else:
        return None

def create_tokenizer(json: str):
    tokenizer = Tokenizer.from_str(json)
    return {"type": "huggingface_tokenizer", "tokenizer": tokenizer}

def create_pretrained_tokenizer(identifier: str, revision="main", auth_token: Optional[str] = None):
    try:
        tokenizer = Tokenizer.from_pretrained(
            identifier, revision=revision, auth_token=auth_token  # type: ignore
        )
    except Exception as e:
        log.error(
            f"Error creating pretrained tokenizer: {e}. Defaulting to version without 'auth_token'."
        )
        tokenizer = Tokenizer.from_pretrained(identifier, revision=revision)
    return {"type": "huggingface_tokenizer", "tokenizer": tokenizer}

def _strip_huggingface_special_token_ids(tokenizer: Tokenizer, tokens: List[int]) -> List[int]:
    try:
        added_tokens_decoder = tokenizer.get_added_tokens_decoder()
    except Exception:
        return tokens

    special_token_ids = {
        token_id
        for token_id, added_token in added_tokens_decoder.items()
        if getattr(added_token, "special", False)
    }
    if not special_token_ids:
        return tokens
    return [token for token in tokens if token not in special_token_ids]