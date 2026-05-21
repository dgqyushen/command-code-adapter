from __future__ import annotations

import json
from typing import Any

import structlog

from cc_adapter.providers.openai.responses_models import ResponseCreateRequest
from cc_adapter.command_code.body import _make_config, make_cc_body
from cc_adapter.command_code.headers import make_cc_headers
from cc_adapter.core.errors import AdapterError
from cc_adapter.providers.shared.model_mapping import (
    resolve_model_id,
    clamp_reasoning_effort,
)
from cc_adapter.providers.shared.tool_mapping import normalize_input_args, normalize_schema

logger = structlog.get_logger(__name__)

RESPONSES_NOT_SUPPORTED = {
    "top_p": "top_p",
    "store": "store",
    "metadata": "metadata",
    "user": "user",
    "truncation": "truncation",
    "service_tier": "service_tier",
    "parallel_tool_calls": "parallel_tool_calls",
    "max_tool_calls": "max_tool_calls",
    "include": "include",
    "safety_identifier": "safety_identifier",
    "prompt_cache_key": "prompt_cache_key",
    "prompt_cache_retention": "prompt_cache_retention",
    "background": "background",
    "top_logprobs": "top_logprobs",
    "context_management": "context_management",
}

RESPONSES_SESSION_PARAMS = {
    "previous_response_id": "previous_response_id",
    "conversation": "conversation",
    "prompt": "prompt",
    "response_format": "response_format",
    "text": "text",
}

SUPPORTED_MESSAGE_ROLES = {"user", "assistant", "system", "developer"}


class ResponsesRequestTranslator:
    def translate(self, req: ResponseCreateRequest) -> tuple[dict[str, Any], dict[str, Any]]:
        self._validate_session_params(req)
        self._warn_unsupported(req)
        self._validate_tools(req)
        cc_body = self._build_body(req)
        cc_headers = make_cc_headers()
        return cc_body, cc_headers

    def _warn_unsupported(self, req: ResponseCreateRequest) -> None:
        for attr in RESPONSES_NOT_SUPPORTED:
            value = getattr(req, attr, None)
            if value is not None:
                logger.warning("Unsupported Responses parameter ignored: %s = %s", attr, value)

    @staticmethod
    def _validate_session_params(req: ResponseCreateRequest) -> None:
        for attr in RESPONSES_SESSION_PARAMS:
            value = getattr(req, attr, None)
            if value is not None:
                raise AdapterError(
                    message=f"Responses parameter '{attr}' is not supported",
                    status_code=400,
                )

    @staticmethod
    def _validate_tools(req: ResponseCreateRequest) -> None:
        if not req.tools:
            return
        for t in req.tools:
            tool_type = t.get("type", "function")
            if tool_type != "function":
                raise AdapterError(
                    message=f"Unsupported tool type '{tool_type}': only 'function' tools are supported",
                    status_code=400,
                )
            name = t.get("name", "")
            if not name:
                raise AdapterError(
                    message="function tool must have a non-empty 'name' field",
                    status_code=400,
                )
            input_schema = t.get("input_schema", t.get("parameters"))
            if input_schema is None:
                raise AdapterError(
                    message="function tool must have an 'input_schema' or 'parameters' field",
                    status_code=400,
                )
            if not isinstance(input_schema, dict):
                raise AdapterError(
                    message="function tool 'input_schema' (or 'parameters') must be a JSON Schema object",
                    status_code=400,
                )

    def _build_body(self, req: ResponseCreateRequest) -> dict[str, Any]:
        params: dict[str, Any] = {
            "model": resolve_model_id(req.model),
            "messages": self._build_messages(req.input),
            "max_tokens": req.max_output_tokens or 64000,
            "stream": True,
        }
        if req.instructions:
            params["system"] = req.instructions
        if req.temperature is not None:
            params["temperature"] = req.temperature
        if req.reasoning:
            effort = req.reasoning.get("effort")
            if effort:
                model_id = resolve_model_id(req.model)
                clamped = clamp_reasoning_effort(model_id, effort)
                if clamped:
                    params["reasoning_effort"] = clamped
        if req.tools:
            params["tools"] = [
                {
                    "name": t.get("name", ""),
                    "description": t.get("description"),
                    "input_schema": normalize_schema(t.get("input_schema", t.get("parameters", {}))),
                }
                for t in req.tools
            ]
        tool_choice = self._translate_tool_choice(req.tool_choice, req.tools)
        if tool_choice is not None:
            params["tool_choice"] = tool_choice
        return make_cc_body(config=_make_config(), params=params)

    @staticmethod
    def _translate_tool_choice(
        tool_choice: str | dict[str, Any] | None, req_tools: list[dict[str, Any]] | None
    ) -> dict[str, Any] | None:
        if tool_choice is None:
            return None
        if isinstance(tool_choice, str):
            if tool_choice == "auto":
                return {"type": "auto"}
            elif tool_choice == "none":
                return {"type": "none"}
            elif tool_choice == "required":
                return {"type": "any"}
        if isinstance(tool_choice, dict):
            tc_type = tool_choice.get("type", "")
            if tc_type in ("auto", "none", "any"):
                return tool_choice
            if tc_type == "function":
                name = tool_choice.get("name", "")
                if name:
                    if not req_tools:
                        raise AdapterError(
                            message=f"tool_choice specifies function '{name}' but no tools are declared",
                            status_code=400,
                        )
                    tool_names = [t.get("name") for t in req_tools]
                    if name not in tool_names:
                        raise AdapterError(
                            message=f"tool_choice function '{name}' does not match any declared tool",
                            status_code=400,
                        )
                    return {"type": "tool", "name": name}
        raise AdapterError(
            message=f"Unsupported tool_choice value: {tool_choice}",
            status_code=400,
        )

    def _build_messages(self, input_data: str | list[dict[str, Any]]) -> list[dict[str, Any]]:
        if isinstance(input_data, str):
            return [{"role": "user", "content": [{"type": "text", "text": input_data}]}]
        messages: list[dict[str, Any]] = []
        tool_names: dict[str, str] = {}
        for item in input_data:
            translated = self._translate_input_item(item, tool_names)
            if translated:
                messages.extend(translated)
        return messages

    def _translate_input_item(self, item: dict[str, Any], tool_names: dict[str, str]) -> list[dict[str, Any]] | None:
        item_type = item.get("type", "")
        if item_type == "message":
            return self._translate_message_item(item, tool_names)
        elif item_type == "function_call":
            return self._translate_function_call_item(item, tool_names)
        elif item_type == "function_call_output":
            call_id = item.get("call_id", "")
            if not call_id:
                raise AdapterError(
                    message="function_call_output item must have a non-empty 'call_id'",
                    status_code=400,
                )
            if call_id not in tool_names:
                raise AdapterError(
                    message=f"function_call_output call_id '{call_id}' does not match any prior function_call",
                    status_code=400,
                )
            return self._translate_function_call_output_item(item, tool_names)
        elif item_type in ("reasoning", "item_reference"):
            raise AdapterError(
                message=f"Input item type '{item_type}' is not supported",
                status_code=400,
            )
        else:
            raise AdapterError(
                message=f"Unsupported input item type '{item_type}'",
                status_code=400,
            )

    def _translate_message_item(self, item: dict[str, Any], tool_names: dict[str, str]) -> list[dict[str, Any]]:
        self._validate_message_item(item)
        role = item.get("role", "user")
        content_raw = item.get("content", "")
        content_blocks: list[dict[str, Any]] = []
        if isinstance(content_raw, str) and content_raw.strip():
            content_blocks.append({"type": "text", "text": content_raw})
        elif isinstance(content_raw, list):
            for block in content_raw:
                if not isinstance(block, dict):
                    raise AdapterError(
                        message="message content blocks must be objects",
                        status_code=400,
                    )
                block_type = block.get("type", "")
                if block_type == "input_text":
                    content_blocks.append({"type": "text", "text": self._non_empty_block_text(block, "input_text")})
                elif block_type == "input_image":
                    raise AdapterError(
                        message="input_image content blocks are not supported",
                        status_code=400,
                    )
                elif block_type == "output_text":
                    content_blocks.append({"type": "text", "text": self._non_empty_block_text(block, "output_text")})
                elif block_type == "refusal":
                    content_blocks.append({"type": "text", "text": self._non_empty_block_text(block, "refusal")})
                else:
                    raise AdapterError(
                        message=f"message content block type '{block_type}' is not supported",
                        status_code=400,
                    )
        if role == "assistant":
            for tool_call in item.get("tool_calls") or []:
                tid, tool_name, args = self._parse_message_tool_call(tool_call)
                tool_names[tid] = tool_name
                content_blocks.append(
                    {
                        "type": "tool-call",
                        "toolCallId": tid,
                        "toolName": tool_name,
                        "input": normalize_input_args(args),
                    }
                )
        if not content_blocks:
            raise AdapterError(
                message=f"message has no supported content for role '{role}'",
                status_code=400,
            )
        return [{"role": role, "content": content_blocks}]

    def _validate_message_item(self, item: dict[str, Any]) -> None:
        role = item.get("role", "user")
        if role not in SUPPORTED_MESSAGE_ROLES:
            raise AdapterError(
                message=f"Unsupported message role '{role}'",
                status_code=400,
            )
        content_raw = item.get("content", "")
        has_tool_calls = role == "assistant" and bool(item.get("tool_calls"))
        if isinstance(content_raw, str) and not content_raw.strip() and not has_tool_calls:
            raise AdapterError(
                message=f"message content is empty for role '{role}'",
                status_code=400,
            )
        if isinstance(content_raw, list) and len(content_raw) == 0 and not has_tool_calls:
            raise AdapterError(
                message=f"message content is an empty list for role '{role}'",
                status_code=400,
            )
        if not isinstance(content_raw, (str, list)):
            raise AdapterError(
                message=f"message content must be a string or list for role '{role}'",
                status_code=400,
            )

    @staticmethod
    def _non_empty_block_text(block: dict[str, Any], block_type: str) -> str:
        key = "refusal" if block_type == "refusal" else "text"
        text = block.get(key, "")
        if not isinstance(text, str) or not text.strip():
            raise AdapterError(
                message=f"{block_type} content block text is empty",
                status_code=400,
            )
        return text

    def _parse_message_tool_call(self, tool_call: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
        if not isinstance(tool_call, dict):
            raise AdapterError(message="assistant tool_calls entries must be objects", status_code=400)
        tid = tool_call.get("id", "")
        if not tid:
            raise AdapterError(message="assistant tool_call must have a non-empty 'id'", status_code=400)
        function = tool_call.get("function") or {}
        if not isinstance(function, dict):
            raise AdapterError(message="assistant tool_call function must be an object", status_code=400)
        tool_name = function.get("name", "")
        if not tool_name:
            raise AdapterError(message="assistant tool_call function must have a non-empty 'name'", status_code=400)
        args = self._parse_json_args(function.get("arguments", "{}"), "assistant tool_call arguments")
        return tid, tool_name, args

    def _translate_function_call_item(self, item: dict[str, Any], tool_names: dict[str, str]) -> list[dict[str, Any]]:
        call_id = item.get("call_id", "")
        name = item.get("name", "")
        if not call_id:
            raise AdapterError(
                message="function_call item must have a non-empty 'call_id'",
                status_code=400,
            )
        if not name:
            raise AdapterError(
                message="function_call item must have a non-empty 'name'",
                status_code=400,
            )
        tool_names[call_id] = name
        return [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool-call",
                        "toolCallId": call_id,
                        "toolName": name,
                        "input": normalize_input_args(
                            self._parse_json_args(item.get("arguments", "{}"), "function_call arguments")
                        ),
                    }
                ],
            }
        ]

    def _translate_function_call_output_item(
        self, item: dict[str, Any], tool_names: dict[str, str]
    ) -> list[dict[str, Any]]:
        call_id = item.get("call_id", "")
        output = item.get("output", "")
        return [
            {
                "role": "tool",
                "content": [
                    {
                        "type": "tool-result",
                        "toolCallId": call_id,
                        "toolName": tool_names.get(call_id, "unknown"),
                        "output": {"type": "text", "value": output if isinstance(output, str) else json.dumps(output)},
                    }
                ],
            }
        ]

    @staticmethod
    def _parse_json_args(raw: Any, label: str = "arguments") -> dict[str, Any]:
        if raw is None or raw == "":
            return {}
        if isinstance(raw, dict):
            return raw
        if not isinstance(raw, str):
            raise AdapterError(
                message=f"{label} must be a JSON object string",
                status_code=400,
            )
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, ValueError) as exc:
            raise AdapterError(
                message=f"{label} must be valid JSON",
                status_code=400,
            ) from exc
        if not isinstance(parsed, dict):
            raise AdapterError(
                message=f"{label} must decode to a JSON object",
                status_code=400,
            )
        return parsed
