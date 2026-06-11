# bound.embedding
## @lineage: channel.bound.embedding
## @lineage: gate.bound.embedding
import asyncio
import contextvars
import datetime
import inspect
import json
import os
import random
import sys
import time
import traceback
from functools import partial
from typing import Any, Coroutine, Dict, List, Literal, Optional, Type, Union
import httpx
import openai
from typing_extensions import overload

from litellm.litellm_core_utils.mock_functions import mock_embedding
from litellm.llms.gemini.common_utils import get_api_key_from_env
from litellm.llms.huggingface.embedding.handler import HuggingFaceEmbedding
from litellm.llms.ollama.completion import handler as ollama

from anchor.model.llms.custom.llm import CustomLLM
from channel.litellm.get_litellm_params import get_litellm_params
from channel.config.resolver import config
from bound.client import client
from channel.litellm.exception_mapping_utils import exception_type
from gov.gate.exceptions import LiteLLMUnknownProvider
from bound.plane import Logging as LiteLLMLoggingObj
from anchor.model.types.utils import (
    CustomPricingLiteLLMParams,
    ModelResponseStream,
    RawRequestTypedDict,
    StreamingChoices,
)
from bound.handler.stream.wrapper import CustomStreamWrapper
from anchor.model.provider.gate import get_optional_params_embeddings
from gov.gate.io.secret.manager import get_secret, get_secret_str
from anchor.model.provider.resolver import get_llm_provider
from bound.token.counter import token_counter
from anchor.model.llms.openai.embedding import OpenAIEmbedding
from anchor.model.types.utils import all_litellm_params, EmbeddingResponse

from channel.switch.params import Choices, Message, ModelResponse
from watcher.plane.emitter import get_emitter

log = get_emitter("bound.embedding")

openai_embedding = OpenAIEmbedding()
huggingface_embed = HuggingFaceEmbedding()

def _build_custom_pricing_entry(
    custom_llm_provider: str,
    kwargs: dict,
    model_info: Optional[dict] = None,
) -> dict:
    entry: dict = {"litellm_provider": custom_llm_provider}

    for field_name in CustomPricingLiteLLMParams.model_fields:
        value = kwargs.get(field_name)
        if value is not None:
            entry[field_name] = value

    if model_info and isinstance(model_info, dict):
        for key in ("mode", "supports_prompt_caching", "max_tokens"):
            if key in model_info and model_info[key] is not None:
                entry.setdefault(key, model_info[key])

    return entry

@client
async def aembedding(*args, **kwargs) -> EmbeddingResponse:
    loop = asyncio.get_event_loop()
    model = args[0] if len(args) > 0 else kwargs["model"]
    ### PASS ARGS TO Embedding ###
    kwargs["aembedding"] = True
    custom_llm_provider = kwargs.get("custom_llm_provider", None)
    try:
        # Use a partial function to pass your keyword arguments
        func = partial(embedding, *args, **kwargs)

        # Add the context to the function
        ctx = contextvars.copy_context()
        func_with_context = partial(ctx.run, func)
        _, custom_llm_provider, _, _ = get_llm_provider(
            model=model,
            custom_llm_provider=custom_llm_provider,
            api_base=kwargs.get("api_base", None),
        )

        # Await normally
        init_response = await loop.run_in_executor(None, func_with_context)

        response: Optional[EmbeddingResponse] = None
        if isinstance(init_response, dict):
            response = EmbeddingResponse(**init_response)
        elif isinstance(init_response, EmbeddingResponse):  ## CACHING SCENARIO
            response = init_response
        elif asyncio.iscoroutine(init_response):
            response = await init_response  # type: ignore
        if (
            response is not None
            and isinstance(response, EmbeddingResponse)
            and hasattr(response, "_hidden_params")
        ):
            response._hidden_params["custom_llm_provider"] = custom_llm_provider

        if response is None:
            raise ValueError(
                "Unable to get Embedding Response. Please pass a valid llm_provider."
            )
        return response
    except Exception as e:
        custom_llm_provider = custom_llm_provider or "openai"
        raise exception_type(
            model=model,
            custom_llm_provider=custom_llm_provider,
            original_exception=e,
            completion_kwargs=args,
            extra_kwargs=kwargs,
        )

@overload
def embedding(
    model,
    input=[],
    # Optional params
    dimensions: Optional[int] = None,
    encoding_format: Optional[str] = None,
    timeout=600,  # default to 10 minutes
    # set api_base, api_version, api_key
    api_base: Optional[str] = None,
    api_version: Optional[str] = None,
    api_key: Optional[str] = None,
    api_type: Optional[str] = None,
    caching: bool = False,
    user: Optional[str] = None,
    custom_llm_provider=None,
    litellm_call_id=None,
    logger_fn=None,
    *,
    aembedding: Literal[True],
    **kwargs,
) -> Coroutine[Any, Any, EmbeddingResponse]: 
    ...


# Overload for when aembedding=False or not specified (returns EmbeddingResponse)
@overload
def embedding(
    model,
    input=[],
    # Optional params
    dimensions: Optional[int] = None,
    encoding_format: Optional[str] = None,
    timeout=600,  # default to 10 minutes
    # set api_base, api_version, api_key
    api_base: Optional[str] = None,
    api_version: Optional[str] = None,
    api_key: Optional[str] = None,
    api_type: Optional[str] = None,
    caching: bool = False,
    user: Optional[str] = None,
    custom_llm_provider=None,
    litellm_call_id=None,
    logger_fn=None,
    *,
    aembedding: Literal[False] = False,
    **kwargs,
) -> EmbeddingResponse: 
    ...

@client
def embedding(  # noqa: PLR0915
    model,
    input=[],
    # Optional params
    dimensions: Optional[int] = None,
    encoding_format: Optional[str] = None,
    timeout=600,  # default to 10 minutes
    # set api_base, api_version, api_key
    api_base: Optional[str] = None,
    api_version: Optional[str] = None,
    api_key: Optional[str] = None,
    api_type: Optional[str] = None,
    caching: bool = False,
    user: Optional[str] = None,
    custom_llm_provider=None,
    litellm_call_id=None,
    logger_fn=None,
    **kwargs,
) -> Union[EmbeddingResponse, Coroutine[Any, Any, EmbeddingResponse]]:
    azure = kwargs.get("azure", None)
    client = kwargs.pop("client", None)
    shared_session = kwargs.get("shared_session", None)
    max_retries = kwargs.get("max_retries", None)
    litellm_logging_obj: LiteLLMLoggingObj = kwargs.get("litellm_logging_obj")  # type: ignore
    mock_response: Optional[List[float]] = kwargs.get("mock_response", None)  # type: ignore
    azure_ad_token_provider = kwargs.get("azure_ad_token_provider", None)
    aembedding: Optional[bool] = kwargs.get("aembedding", None)
    extra_headers = kwargs.get("extra_headers", None)
    headers = kwargs.get("headers", None) or extra_headers
    if headers is None:
        headers = {}
    if extra_headers is not None:
        headers.update(extra_headers)
    if config.proxy_auth is not None:
        try:
            proxy_headers = config.proxy_auth.get_auth_headers()
            headers.update(proxy_headers)
        except Exception as e:
            log.warning(f"Failed to get proxy auth headers: {e}")
    ### CUSTOM MODEL COST ###
    input_cost_per_token = kwargs.get("input_cost_per_token", None)
    output_cost_per_token = kwargs.get("output_cost_per_token", None)
    input_cost_per_second = kwargs.get("input_cost_per_second", None)
    openai_params = [
        "user",
        "dimensions",
        "request_timeout",
        "api_base",
        "api_version",
        "api_key",
        "deployment_id",
        "organization",
        "base_url",
        "default_headers",
        "timeout",
        "max_retries",
        "encoding_format",
    ]
    litellm_params = [
        "aembedding",
        "extra_headers",
    ] + all_litellm_params

    default_params = openai_params + litellm_params
    non_default_params = {
        k: v for k, v in kwargs.items() if k not in default_params
    }  # model-specific params - pass them straight to the model/provider

    model, custom_llm_provider, dynamic_api_key, api_base = get_llm_provider(
        model=model,
        custom_llm_provider=custom_llm_provider,
        api_base=api_base,
        api_key=api_key,
    )

    if dynamic_api_key is not None:
        api_key = dynamic_api_key

    allowed_openai_params: Optional[List[str]] = kwargs.get(
        "allowed_openai_params", None
    )
    optional_params = get_optional_params_embeddings(
        model=model,
        user=user,
        dimensions=dimensions,
        encoding_format=encoding_format,
        custom_llm_provider=custom_llm_provider,
        allowed_openai_params=allowed_openai_params,
        **non_default_params,
    )

    if (input_cost_per_token is not None and output_cost_per_token is not None) or input_cost_per_second is not None:
        config.register_model(
            {
                f"{custom_llm_provider}/{model}": _build_custom_pricing_entry(
                    custom_llm_provider=custom_llm_provider,
                    kwargs=kwargs,
                    model_info=kwargs.get("model_info"),
                )
            }
        )

    litellm_params_dict = get_litellm_params(**kwargs)

    logging: LiteLLMLoggingObj = litellm_logging_obj  # type: ignore
    logging.update_environment_variables(
        model=model,
        user=user,
        optional_params=optional_params,
        litellm_params=litellm_params_dict,
        custom_llm_provider=custom_llm_provider,
    )

    if mock_response is not None:
        return mock_embedding(model=model, mock_response=mock_response)

    try:
        response: Optional[Union[EmbeddingResponse, Coroutine[Any, Any, EmbeddingResponse]]] = None
        if (custom_llm_provider == "openai" or (model in config.open_ai_embedding_models and custom_llm_provider is None)):
            api_base = (
                api_base
                or config.api_base
                or get_secret_str("OPENAI_BASE_URL")
                or get_secret_str("OPENAI_API_BASE")
                or "https://api.openai.com/v1"
            )
            openai.organization = config.organization or get_secret_str("OPENAI_ORGANIZATION") or None
            api_key = api_key or config.api_key or config.openai_key or get_secret_str("OPENAI_API_KEY")
            if headers is not None and headers != {}:
                optional_params["extra_headers"] = headers

            if encoding_format is not None:
                optional_params["encoding_format"] = encoding_format
            else:
                env_fmt = get_secret_str("LITELLM_DEFAULT_EMBEDDING_ENCODING_FORMAT")
                if env_fmt is not None and env_fmt.strip().lower() == "none":
                    optional_params.pop("encoding_format", None)
                else:
                    _default_fmt = (
                        optional_params.get("encoding_format") or env_fmt or "float"
                    )
                    if _default_fmt.strip().lower() == "none":
                        optional_params.pop("encoding_format", None)
                    else:
                        optional_params["encoding_format"] = _default_fmt

            api_version = None

            ## EMBEDDING CALL
            ctx = openai_embedding.embedding(
                model=model,
                input=input,
                api_base=api_base,
                api_key=api_key,
                logging_obj=logging,
                timeout=timeout,
                optional_params=optional_params,
                client=client,
                aembedding=aembedding,
                max_retries=max_retries,
                shared_session=shared_session,
            )
            response = openai_embedding.embedding(ctx=ctx, model_response=EmbeddingResponse)
        elif custom_llm_provider == "huggingface":
            api_key = api_key or config.huggingface_key or get_secret("HUGGINGFACE_API_KEY") or litellm.api_key
            response = huggingface_embed.embedding(
                model=model,
                input=input,
                api_key=api_key,
                api_base=api_base,
                logging_obj=logging,
                model_response=EmbeddingResponse(),
                optional_params=optional_params,
                client=client,
                aembedding=aembedding,
                litellm_params=litellm_params_dict,
                headers=headers,
            )
        elif custom_llm_provider == "ollama":
            api_base = config.api_base or api_base or get_secret_str("OLLAMA_API_BASE") or "http://localhost:11434"
            if isinstance(input, str):
                input = [input]
            if not all(isinstance(item, str) for item in input):
                raise litellm.BadRequestError(
                    message=f"Invalid input for ollama embeddings. input={input}",
                    model=model,  # type: ignore
                    llm_provider="ollama",  # type: ignore
                )
            ollama_embeddings_fn = (
                ollama.ollama_aembeddings
                if aembedding is True
                else ollama.ollama_embeddings
            )
            response = ollama_embeddings_fn(  # type: ignore
                api_base=api_base,
                model=model,
                prompts=input,
                logging_obj=logging,
                optional_params=optional_params,
                model_response=EmbeddingResponse(),
            )
        elif custom_llm_provider in litellm._custom_providers:
            custom_handler: Optional[CustomLLM] = None
            for item in config.custom_provider_map:
                if item["provider"] == custom_llm_provider:
                    custom_handler = item["custom_handler"]

            if custom_handler is None:
                raise LiteLLMUnknownProvider(
                    model=model, custom_llm_provider=custom_llm_provider
                )

            handler_fn = (
                custom_handler.embedding
                if not aembedding
                else custom_handler.aembedding
            )

            response = handler_fn(
                model=model,
                input=input,
                logging_obj=logging,
                api_base=api_base,
                api_key=api_key,
                timeout=timeout,
                optional_params=optional_params,
                model_response=EmbeddingResponse(),
                print_verbose=print_verbose,
                litellm_params=litellm_params_dict,
            )
        else:
            raise LiteLLMUnknownProvider(model=model, custom_llm_provider=custom_llm_provider)

        if (
            response is not None
            and hasattr(response, "_hidden_params")
            and isinstance(response, EmbeddingResponse)
        ):
            response._hidden_params["custom_llm_provider"] = custom_llm_provider

        if response is None:
            raise LiteLLMUnknownProvider(
                model=model, custom_llm_provider=custom_llm_provider
            )
        return response
    except Exception as e:
        ## LOGGING
        litellm_logging_obj.post_call(
            input=input,
            api_key=api_key,
            original_response=str(e),
        )
        ## Map to OpenAI Exception
        raise exception_type(
            model=model,
            original_exception=e,
            custom_llm_provider=custom_llm_provider,
            extra_kwargs=kwargs,
        )

def print_verbose(print_statement):
    try:
        log.debug(print_statement)
        if config.set_verbose:
            print(print_statement)  # noqa
    except Exception:
        pass