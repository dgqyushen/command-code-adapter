from __future__ import annotations

import json
from typing import Any

import structlog

from cc_adapter.providers.openai.responses_models import ResponseCreateRequest
from cc_adapter.command_code.body import _make_config, make_cc_body
from cc_adapter.command_code.headers import make_cc_headers
from cc_adapter.providers.shared.model_mapping import (
    MODEL_PROVIDER_MAP,
    REASONING_EFFORT_MAX,
    REASONING_EFFORT_MAP,
)
from cc_adapter.providers.shared.tool_mapping import normalize_input_args, normalize_schema
from cc_adapter.core.utils import is_deepseek_v4_model

logger = structlog.get_logger(__name__)

RESPONSES_NOT_SUPPORTED = {
    "top_p": "top_p",
    "store": "store",
    "metadata": "metadata",
    "user": "user",
    "response_format": "response_format",
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
    "previous_response_id": "previous_response_id",
    "conversation": "conversation",
    "prompt": "prompt",
    "context_management": "context_management",
    "text": "text",
}


class ResponsesRequestTranslator:
    def translate(self, req: ResponseCreateRequest) -> tuple[dict[str, Any], dict[str, Any]]:
        self._warn_unsupported(req)
        cc_body = self._build_body(req)
        cc_headers = make_cc_headers()
        return cc_body, cc_headers

    def _warn_unsupported(self, req: ResponseCreateRequest) -> None:
        for attr in RESPONSES_NOT_SUPPORTED:
            value = getattr(req, attr, None)
            if value is not None:
                logger.warning("Unsupported Responses parameter ignored: %s = %s", attr, value)

    @staticmethod
    def _normalize_model(model: str) -> str:
        return MODEL_PROVIDER_MAP.get(model, model)

    def _build_body(self, req: ResponseCreateRequest) -> dict[str, Any]:
        params: dict[str, Any] = {
            "model": self._normalize_model(req.model),
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
                model_id = self._normalize_model(req.model)
                if is_deepseek_v4_model(model_id) and effort in ("xhigh", "max"):
                    params["reasoning_effort"] = "max"
                    current_system = params.get("system", "")
                    params["system"] = (
                        f"{REASONING_EFFORT_MAX}{current_system}" if current_system else REASONING_EFFORT_MAX
                    )
                else:
                    params["reasoning_effort"] = effort
                    instruction = REASONING_EFFORT_MAP.get(effort, "")
                    if instruction:
                        current_system = params.get("system", "")
                        params["system"] = f"{current_system}\n{instruction}" if current_system else instruction
        if req.tools:
            function_tools = []
            for t in req.tools:
                tool_type = t.get("type", "function")
                if tool_type != "function":
                    logger.warning("Unsupported built-in tool type skipped: %s", tool_type)
                    continue
                function_tools.append(t)
            params["tools"] = [
                {
                    "name": t.get("name", ""),
                    "description": t.get("description"),
                    "input_schema": normalize_schema(t.get("input_schema", t.get("parameters", {}))),
                }
                for t in function_tools
            ]
        tool_choice = self._translate_tool_choice(req.tool_choice)
        if tool_choice is not None:
            params["tool_choice"] = tool_choice
        return make_cc_body(config=_make_config(), params=params)

    @staticmethod
    def _translate_tool_choice(tool_choice: str | dict[str, Any] | None) -> dict[str, Any] | None:
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
            name = tool_choice.get("name", "")
            if name:
                return {"type": "tool", "name": name}
        return {"type": "auto"}

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
            return self._translate_function_call_output_item(item, tool_names)
        elif item_type in ("reasoning", "item_reference"):
            return None
        else:
            logger.warning("Unsupported input item type skipped: %s", item_type)
            return None

    def _translate_message_item(self, item: dict[str, Any], tool_names: dict[str, str]) -> list[dict[str, Any]]:
        role = item.get("role", "user")
        content_raw = item.get("content", "")
        content_blocks: list[dict[str, Any]] = []
        if isinstance(content_raw, str):
            content_blocks.append({"type": "text", "text": content_raw})
        elif isinstance(content_raw, list):
            for block in content_raw:
                block_type = block.get("type", "")
                if block_type == "input_text":
                    content_blocks.append({"type": "text", "text": block.get("text", "")})
                elif block_type == "input_image":
                    logger.warning("Image input not supported, skipping")
                else:
                    content_blocks.append({"type": "text", "text": str(block)})
        if role == "assistant":
            for tool_call in item.get("tool_calls") or []:
                tid = tool_call.get("id", "")
                tool_names[tid] = tool_call.get("function", {}).get("name", "")
                content_blocks.append(
                    {
                        "type": "tool-call",
                        "toolCallId": tid,
                        "toolName": tool_call.get("function", {}).get("name", ""),
                        "input": normalize_input_args(
                            self._parse_json_args(tool_call.get("function", {}).get("arguments", "{}"))
                        ),
                    }
                )
        return [{"role": role, "content": content_blocks}]

    def _translate_function_call_item(self, item: dict[str, Any], tool_names: dict[str, str]) -> list[dict[str, Any]]:
        call_id = item.get("call_id", "")
        name = item.get("name", "")
        tool_names[call_id] = name
        return [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool-call",
                        "toolCallId": call_id,
                        "toolName": name,
                        "input": normalize_input_args(self._parse_json_args(item.get("arguments", "{}"))),
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
    def _parse_json_args(raw: str) -> dict[str, Any]:
        try:
            parsed = json.loads(raw or "{}")
            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, ValueError):
            return {}
