# anchor.switch.model.token.trim
## @lineage: anchor.model.token.trim
import os
import copy
from typing import Any, Dict, List, Optional, Union
from anchor.switch.model.token.counter import token_counter
from anchor.switch.config.constants import (
    DEFAULT_CHAT_COMPLETION_PARAM_VALUES,
    DEFAULT_EMBEDDING_PARAM_VALUES,
    DEFAULT_MAX_LRU_CACHE_SIZE,
    DEFAULT_TRIM_RATIO,
    FUNCTION_DEFINITION_TOKEN_COUNT,
    INITIAL_RETRY_DELAY,
    JITTER,
    MAX_RETRY_DELAY,
    MAX_TOKEN_TRIMMING_ATTEMPTS,
    MINIMUM_PROMPT_CACHE_TOKEN_COUNT,
    OPENAI_EMBEDDING_PARAMS,
    TOOL_CHOICE_OBJECT_TOKEN_COUNT,
)
from anchor.surface.model.cost.map import model_cost
from watcher.plane.emitter import get_emitter

log = get_emitter("token.trim")

def trim_messages(
    messages,
    model: Optional[str] = None,
    trim_ratio: float = DEFAULT_TRIM_RATIO,
    return_response_tokens: bool = False,
    max_tokens=None,
):
    original_messages = messages
    messages = copy.deepcopy(messages)
    try:
        if max_tokens is None:
            if model in model_cost:
                max_tokens_for_model = model_cost[model].get("max_input_tokens", model_cost[model]["max_tokens"])
                max_tokens = int(max_tokens_for_model * trim_ratio)
            else:
                return messages

        system_message = ""
        for message in messages:
            if message["role"] == "system":
                system_message += "\n" if system_message else ""
                system_message += message["content"]

        tool_messages = []
        for message in reversed(messages):
            if message["role"] != "tool":
                break
            tool_messages.append(message)
        tool_messages.reverse()
        if len(tool_messages):
            messages = messages[: -len(tool_messages)]

        current_tokens = token_counter(model=model or "", messages=messages)
        print_verbose(f"Current tokens: {current_tokens}, max tokens: {max_tokens}")

        # Do nothing if current tokens under messages
        if current_tokens < max_tokens:
            return messages + tool_messages

        #### Trimming messages if current_tokens > max_tokens
        print_verbose(
            f"Need to trim input messages: {messages}, current_tokens{current_tokens}, max_tokens: {max_tokens}"
        )
        system_message_event: Optional[dict] = None
        if system_message:
            system_message_event, max_tokens = process_system_message(
                system_message=system_message, max_tokens=max_tokens, model=model
            )

            if max_tokens == 0:  # the system messages are too long
                return [system_message_event]

            # Since all system messages are combined and trimmed to fit the max_tokens,
            # we remove all system messages from the messages list
            messages = [message for message in messages if message["role"] != "system"]

        log.debug(f"Processed system message: {system_message_event}")
        final_messages = process_messages(messages=messages, max_tokens=max_tokens, model=model)
        log.debug(f"Processed messages: {final_messages}")

        # Add system message to the beginning of the final messages
        if system_message_event:
            final_messages = [system_message_event] + final_messages

        if len(tool_messages) > 0:
            final_messages.extend(tool_messages)

        log.debug(f"Final messages: {final_messages}, return_response_tokens: {return_response_tokens}")
        if return_response_tokens:
            response_tokens = max_tokens - get_token_count(final_messages, model)
            return final_messages, response_tokens
        return final_messages
    except Exception as e:
        log.exception("Got exception while token trimming - {}".format(str(e)))
        return original_messages

def process_system_message(system_message, max_tokens, model):
    system_message_event = {"role": "system", "content": system_message}
    systlogens = get_token_count([system_message_event], model)

    if system_message_tokens > max_tokens:
        print_verbose("`tokentrimmer`: Warning, system message exceeds token limit. Trimming...")
        new_system_message = shorten_message_to_fit_limit(system_message_event, max_tokens, model)
        system_message_tokens = get_token_count([new_system_message], model)
    return system_message_event, max_tokens - system_message_tokens

def shorten_message_to_fit_limit(message, tokens_needed, model: Optional[str], raise_error_on_max_limit: bool = False):
    if model is not None and "gpt" in model and tokens_needed <= 10:
        return message

    content = message["content"]
    attempts = 0
    log.debug(f"content: {content}")
    while attempts < MAX_TOKEN_TRIMMING_ATTEMPTS:
        log.debug(f"getting token count for message: {message}")
        total_tokens = get_token_count([message], model)
        log.debug(f"total_tokens: {total_tokens}, tokens_needed: {tokens_needed}")
        if total_tokens <= tokens_needed:
            break

        ratio = (tokens_needed) / total_tokens
        new_length = int(len(content) * ratio) - 1
        new_length = max(0, new_length)

        half_length = new_length // 2
        left_half = content[:half_length]
        right_half = content[-half_length:]

        trimmed_content = left_half + ".." + right_half
        message["content"] = trimmed_content
        log.debug(f"trimmed_content: {trimmed_content}")
        content = trimmed_content
        attempts += 1

    if attempts >= MAX_TOKEN_TRIMMING_ATTEMPTS and raise_error_on_max_limit:
        raise Exception(f"Failed to trim message to fit within {tokens_needed} tokens after {MAX_TOKEN_TRIMMING_ATTEMPTS} attempts")
    return message
