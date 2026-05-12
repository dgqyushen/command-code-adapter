from __future__ import annotations

import copy
import datetime
import json
import logging
from typing import Any

from cc_adapter.models.openai import ChatCompletionRequest
from cc_adapter._tool_mapping import normalize_input_args, normalize_schema
from cc_adapter._shared import MODEL_PROVIDER_MAP, REASONING_EFFORT_MAX, REASONING_EFFORT_MAP, NOT_SUPPORTED_PARAMS
from cc_adapter._body import make_cc_body, _make_config
from cc_adapter._utils import is_deepseek_v4_model
from cc_adapter.headers import make_cc_headers

logger = logging.getLogger(__name__)


class RequestTranslator:
    def translate(self, req: ChatCompletionRequest) -> tuple[dict[str, Any], dict[str, Any]]:
        self._warn_unsupported(req)
        system_prompt, messages = self._split_messages(req.messages)
        cc_body = self._build_body(req, system_prompt, messages)
        cc_headers = self._build_headers()
        return cc_body, cc_headers

    def _warn_unsupported(self, req: ChatCompletionRequest) -> None:
        for attr, name in NOT_SUPPORTED_PARAMS.items():
            value = getattr(req, attr, None)
            if value is not None:
                logger.warning("Unsupported parameter ignored: %s = %s", name, value)

    @staticmethod
    def _translate_tool_choice(tool_choice: Any) -> dict[str, Any] | None:
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
            name = (tool_choice.get("function") or {}).get("name")
            if name:
                return {"type": "tool", "name": name}
        return {"type": "auto"}

    @staticmethod
    def _wrap_content(content: str | None) -> list[dict[str, Any]]:
        return [{"type": "text", "text": content or ""}]

    @staticmethod
    def _parse_tool_arguments(raw: str) -> dict[str, Any]:
        try:
            parsed = json.loads(raw or "{}")
        except ValueError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _tool_call_block(self, tool_call) -> dict[str, Any]:
        return {
            "type": "tool-call",
            "toolCallId": tool_call.id,
            "toolName": tool_call.function.name,
            "input": normalize_input_args(self._parse_tool_arguments(tool_call.function.arguments)),
        }

    def _split_messages(self, messages):
        system_prompt = None
        others = []
        tool_names_by_id: dict[str, str] = {}
        for msg in messages:
            if msg.role == "system":
                system_prompt = msg.content
            elif msg.role == "tool":
                tool_call_id = msg.tool_call_id or ""
                d: dict[str, Any] = {
                    "role": "tool",
                    "content": [
                        {
                            "type": "tool-result",
                            "toolCallId": tool_call_id,
                            "toolName": tool_names_by_id.get(tool_call_id, "unknown"),
                            "output": {"type": "text", "value": msg.content or ""},
                        }
                    ],
                }
                others.append(d)
            else:
                content = []
                if msg.content:
                    content.extend(self._wrap_content(msg.content))
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        tool_names_by_id[tc.id] = tc.function.name
                        content.append(self._tool_call_block(tc))
                if not content:
                    content = self._wrap_content(msg.content)
                d = {"role": msg.role, "content": content}
                if msg.name:
                    d["name"] = msg.name
                others.append(d)
        return system_prompt, others

    @staticmethod
    def _normalize_model(model: str) -> str:
        return MODEL_PROVIDER_MAP.get(model, model)

    def _build_body(self, req: ChatCompletionRequest, system_prompt: str | None, messages: list) -> dict:
        params: dict[str, Any] = {
            "model": self._normalize_model(req.model),
            "messages": messages,
            "max_tokens": req.max_tokens or 64000,
            "stream": req.stream,
        }
        if system_prompt:
            params["system"] = system_prompt
        if req.temperature is not None:
            params["temperature"] = req.temperature
        if req.reasoning_effort is not None:
            effort = req.reasoning_effort
            if is_deepseek_v4_model(req.model) and effort in ("xhigh", "max"):
                params["reasoning_effort"] = "max"
                if system_prompt:
                    params["system"] = f"{REASONING_EFFORT_MAX}{system_prompt}"
                else:
                    params["system"] = REASONING_EFFORT_MAX
            else:
                params["reasoning_effort"] = effort
                instruction = REASONING_EFFORT_MAP.get(effort, "")
                if instruction:
                    if system_prompt:
                        params["system"] = f"{system_prompt}\n{instruction}"
                    else:
                        params["system"] = instruction
        if req.tools:
            params["tools"] = [
                {
                    "name": t.function.name,
                    "description": t.function.description,
                    "input_schema": normalize_schema(t.function.parameters or {}),
                }
                for t in req.tools
            ]
            tool_choice = self._translate_tool_choice(req.tool_choice)
            if tool_choice is not None:
                params["tool_choice"] = tool_choice
        return make_cc_body(config=_make_config(), params=params)

    def _build_headers(self) -> dict[str, str]:
        return make_cc_headers()
