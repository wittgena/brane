# xphi.reflect.dsp.adapter
## @lineage: xphi.opt.dsp.adapter
## @lineage: bound.xor.dsp.adapter
## @lineage: xor.dsp.adapter
## @lineage: bound.channel.bridge.dsp.adapter
## @lineage: channel.bridge.dsp.adapter
## @lineage: meta.xor.adapter.base
## @lineage: xor.adapter.base
import logging
from typing import Any, get_origin
import json_repair

from xphi.xor.opt.basetype import Type
from xphi.xor.opt.basetype import split_message_content_for_custom_types
from anchor.provider.llm.base import BaseLM
from xphi.xor.opt.manifold.history import History
from xphi.xor.opt.manifold.tool import Tool, ToolCalls

from xphi.reflect.dsp.model.reasoning import Reasoning
from xphi.xor.opt.manifold.citation import Citations

from xphi.reflect.dsp.handler.stream.callback import BaseCallback, with_callbacks
from xphi.reflect.dsp.exceptions import AdapterParseError

from arch.xor.manifold.sign.signature import Signature
from watcher.plane.emitter import get_emitter

log = get_emitter(__name__)

_DEFAULT_NATIVE_RESPONSE_TYPES = [Citations, Reasoning]


class Adapter:
    def __init__(
        self,
        callbacks: list[BaseCallback] | None = None,
        use_native_function_calling: bool = False,
        native_response_types: list[type[Type]] | None = None,
    ):
        self.callbacks = callbacks or []
        self.use_native_function_calling = use_native_function_calling
        self.native_response_types = native_response_types or _DEFAULT_NATIVE_RESPONSE_TYPES

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)

        # Decorate format() and parse() method with with_callbacks
        cls.format = with_callbacks(cls.format)
        cls.parse = with_callbacks(cls.parse)

    def _call_preprocess(
        self,
        lm: BaseLM,
        lm_kwargs: dict[str, Any],
        signature: type[Signature],
        inputs: dict[str, Any],
    ) -> type[Signature]:
        if self.use_native_function_calling:
            tool_call_input_field_name = self._get_tool_call_input_field_name(signature)
            tool_call_output_field_name = self._get_tool_call_output_field_name(signature)

            if tool_call_output_field_name and tool_call_input_field_name is None:
                raise ValueError(
                    f"You provided an output field {tool_call_output_field_name} to receive the tool calls information, "
                    "but did not provide any tools as the input. Please provide a list of tools as the input by adding an "
                    "input field with type `list[Tool]`."
                )

            if tool_call_output_field_name and lm.supports_function_calling:
                tools = inputs[tool_call_input_field_name]
                tools = tools if isinstance(tools, list) else [tools]

                lm_tools = [tool.format_as_litellm_function_call() for tool in tools]

                lm_kwargs["tools"] = lm_tools

                signature_for_native_function_calling = signature.delete(tool_call_output_field_name)
                signature_for_native_function_calling = signature_for_native_function_calling.delete(
                    tool_call_input_field_name
                )

                return signature_for_native_function_calling

        # Handle custom types that use native LM features, e.g., reasoning, citations, etc.
        for name, field in signature.output_fields.items():
            if (
                isinstance(field.annotation, type)
                and field.annotation in self.native_response_types
                and issubclass(field.annotation, Type)
            ):
                signature = field.annotation.adapt_to_native_lm_feature(signature, name, lm, lm_kwargs)

        return signature

    def _call_postprocess(
        self,
        processed_signature: type[Signature],
        original_signature: type[Signature],
        outputs: list[dict[str, Any] | str],
        lm: BaseLM,
        lm_kwargs: dict[str, Any],
    ) -> list[dict[str, Any]]:
        values = []

        tool_call_output_field_name = self._get_tool_call_output_field_name(original_signature)

        for output in outputs:
            output_logprobs = None
            tool_calls = None
            text = output

            if isinstance(output, dict):
                text = output["text"]
                output_logprobs = output.get("logprobs")
                tool_calls = output.get("tool_calls")

            if text:
                value = self.parse(processed_signature, text)
                for field_name in original_signature.output_fields.keys():
                    if field_name not in value:
                        # We need to set the field not present in the processed signature to None for consistency.
                        value[field_name] = None
            elif tool_calls and tool_call_output_field_name:
                value = {}
                for field_name in original_signature.output_fields.keys():
                    value[field_name] = None
            else:
                raise AdapterParseError(
                    adapter_name=type(self).__name__,
                    signature=original_signature,
                    lm_response=str(output),
                    message="The LM returned an empty or null response.",
                )

            if tool_calls and tool_call_output_field_name:
                tool_calls = [
                    {
                        "name": v["function"]["name"],
                        "args": json_repair.loads(v["function"]["arguments"]),
                    }
                    for v in tool_calls
                ]
                value[tool_call_output_field_name] = ToolCalls.from_dict_list(tool_calls)

            # Parse custom types that does not rely on the `Adapter.parse()` method
            for name, field in original_signature.output_fields.items():
                if (
                    isinstance(field.annotation, type)
                    and field.annotation in self.native_response_types
                    and issubclass(field.annotation, Type)
                ):
                    parsed_value = field.annotation.parse_lm_response(output)
                    if parsed_value is not None:
                        value[name] = parsed_value

            if output_logprobs:
                value["logprobs"] = output_logprobs

            values.append(value)

        return values

    def __call__(
        self,
        lm: BaseLM,
        lm_kwargs: dict[str, Any],
        signature: type[Signature],
        demos: list[dict[str, Any]],
        inputs: dict[str, Any],
    ) -> list[dict[str, Any]]:
        processed_signature = self._call_preprocess(lm, lm_kwargs, signature, inputs)
        inputs = self.format(processed_signature, demos, inputs)

        outputs = lm(messages=inputs, **lm_kwargs)
        return self._call_postprocess(processed_signature, signature, outputs, lm, lm_kwargs)

    async def acall(
        self,
        lm: BaseLM,
        lm_kwargs: dict[str, Any],
        signature: type[Signature],
        demos: list[dict[str, Any]],
        inputs: dict[str, Any],
    ) -> list[dict[str, Any]]:
        processed_signature = self._call_preprocess(lm, lm_kwargs, signature, inputs)
        inputs = self.format(processed_signature, demos, inputs)

        outputs = await lm.acall(messages=inputs, **lm_kwargs)
        return self._call_postprocess(processed_signature, signature, outputs, lm, lm_kwargs)

    def format(
        self,
        signature: type[Signature],
        demos: list[dict[str, Any]],
        inputs: dict[str, Any],
    ) -> list[dict[str, Any]]:
        inputs_copy = dict(inputs)

        history_field_name = self._get_history_field_name(signature)
        if history_field_name:
            # In order to format the conversation history, we need to remove the history field from the signature.
            signature_without_history = signature.delete(history_field_name)
            conversation_history = self.format_conversation_history(
                signature_without_history,
                history_field_name,
                inputs_copy,
            )

        messages = []
        system_message = self.format_system_message(signature)
        messages.append({"role": "system", "content": system_message})
        messages.extend(self.format_demos(signature, demos))
        if history_field_name:
            # Conversation history and current input
            content = self.format_user_message_content(signature_without_history, inputs_copy, main_request=True)
            messages.extend(conversation_history)
            messages.append({"role": "user", "content": content})
        else:
            # Only current input
            content = self.format_user_message_content(signature, inputs_copy, main_request=True)
            messages.append({"role": "user", "content": content})

        messages = split_message_content_for_custom_types(messages)
        return messages

    def format_system_message(self, signature: type[Signature]) -> str:
        return (
            f"{self.format_field_description(signature)}\n"
            f"{self.format_field_structure(signature)}\n"
            f"{self.format_task_description(signature)}"
        )

    def format_field_description(self, signature: type[Signature]) -> str:
        raise NotImplementedError

    def format_field_structure(self, signature: type[Signature]) -> str:
        raise NotImplementedError

    def format_task_description(self, signature: type[Signature]) -> str:
        raise NotImplementedError

    def format_user_message_content(
        self,
        signature: type[Signature],
        inputs: dict[str, Any],
        prefix: str = "",
        suffix: str = "",
        main_request: bool = False,
    ) -> str:
        raise NotImplementedError

    def format_assistant_message_content(
        self,
        signature: type[Signature],
        outputs: dict[str, Any],
        missing_field_message: str | None = None,
    ) -> str:
        raise NotImplementedError

    def format_demos(self, signature: type[Signature], demos: list[dict[str, Any]]) -> list[dict[str, Any]]:
        complete_demos = []
        incomplete_demos = []

        for demo in demos:
            # Check if all fields are present and not None
            is_complete = all(k in demo and demo[k] is not None for k in signature.fields)

            # Check if demo has at least one input and one output field
            has_input = any(k in demo for k in signature.input_fields)
            has_output = any(k in demo for k in signature.output_fields)

            if is_complete:
                complete_demos.append(demo)
            elif has_input and has_output:
                # We only keep incomplete demos that have at least one input and one output field
                incomplete_demos.append(demo)

        messages = []

        incomplete_demo_prefix = "This is an example of the task, though some input or output fields are not supplied."
        for demo in incomplete_demos:
            messages.append(
                {
                    "role": "user",
                    "content": self.format_user_message_content(signature, demo, prefix=incomplete_demo_prefix),
                }
            )
            messages.append(
                {
                    "role": "assistant",
                    "content": self.format_assistant_message_content(
                        signature, demo, missing_field_message="Not supplied for this particular example. "
                    ),
                }
            )

        for demo in complete_demos:
            messages.append({"role": "user", "content": self.format_user_message_content(signature, demo)})
            messages.append(
                {
                    "role": "assistant",
                    "content": self.format_assistant_message_content(
                        signature, demo, missing_field_message="Not supplied for this conversation history message. "
                    ),
                }
            )

        return messages

    def _get_history_field_name(self, signature: type[Signature]) -> bool:
        for name, field in signature.input_fields.items():
            if field.annotation == History:
                return name
        return None

    def _get_tool_call_input_field_name(self, signature: type[Signature]) -> bool:
        for name, field in signature.input_fields.items():
            origin = get_origin(field.annotation)
            if origin is list and field.annotation.__args__[0] == Tool:
                return name
            if field.annotation == Tool:
                return name
        return None

    def _get_tool_call_output_field_name(self, signature: type[Signature]) -> bool:
        for name, field in signature.output_fields.items():
            if field.annotation == ToolCalls:
                return name
        return None

    def format_conversation_history(
        self,
        signature: type[Signature],
        history_field_name: str,
        inputs: dict[str, Any],
    ) -> list[dict[str, Any]]:
        conversation_history = inputs[history_field_name].messages if history_field_name in inputs else None

        if conversation_history is None:
            return []

        messages = []
        for message in conversation_history:
            messages.append(
                {
                    "role": "user",
                    "content": self.format_user_message_content(signature, message),
                }
            )
            messages.append(
                {
                    "role": "assistant",
                    "content": self.format_assistant_message_content(signature, message),
                }
            )

        # Remove the history field from the inputs
        del inputs[history_field_name]

        return messages

    def parse(self, signature: type[Signature], completion: str) -> dict[str, Any]:
        raise NotImplementedError
