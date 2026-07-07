from __future__ import annotations

import copy
import datetime
import structlog
from typing import Any

from cc_adapter.providers.openai.models import ChatCompletionRequest
from cc_adapter.providers.shared.tool_mapping import (
    make_tool_call_block,
    make_tool_result_block,
    normalize_schema,
    translate_tool_choice,
)
from cc_adapter.providers.shared.model_mapping import (
    resolve_model_id,
    clamp_reasoning_effort,
    NOT_SUPPORTED_PARAMS,
)
from cc_adapter.command_code.body import make_cc_body, make_config
from cc_adapter.command_code.headers import make_cc_headers

logger = structlog.get_logger(__name__)


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
        return translate_tool_choice(tool_choice)

    @staticmethod
    def _wrap_content(content: str | None) -> list[dict[str, Any]]:
        return [{"type": "text", "text": content or ""}]

    @staticmethod
    def _translate_image_url(part: dict) -> dict[str, Any]:
        image_url = part.get("image_url", {})
        url = image_url.get("url", "") if isinstance(image_url, dict) else str(image_url)
        return {"type": "image", "image": url}

    @staticmethod
    def _build_content_parts(content: str | list[dict] | None) -> list[dict[str, Any]]:
        if content is None:
            return []
        if isinstance(content, str):
            return [{"type": "text", "text": content}]
        parts = []
        for part in content:
            if not isinstance(part, dict):
                parts.append({"type": "text", "text": str(part)})
            elif part.get("type") == "image_url":
                parts.append(RequestTranslator._translate_image_url(part))
            elif part.get("type") == "text":
                parts.append({"type": "text", "text": part.get("text", "")})
        return parts

    @staticmethod
    def _parse_tool_arguments(raw: str) -> dict[str, Any]:
        from cc_adapter.core.utils import parse_tool_arguments

        return parse_tool_arguments(raw)

    def _tool_call_block(self, tool_call) -> dict[str, Any]:
        return make_tool_call_block(
            tool_call.id,
            tool_call.function.name,
            self._parse_tool_arguments(tool_call.function.arguments),
        )

    def _split_messages(self, messages: list[Any]) -> tuple[str | None, list[dict[str, Any]]]:
        system_prompt = None
        others = []
        tool_names_by_id: dict[str, str] = {}
        for msg in messages:
            if msg.role == "system":
                system_prompt = msg.content if isinstance(msg.content, str) else None
            elif msg.role == "tool":
                tool_call_id = msg.tool_call_id or ""
                d: dict[str, Any] = {
                    "role": "tool",
                    "content": [
                        make_tool_result_block(
                            tool_call_id,
                            tool_names_by_id.get(tool_call_id, "unknown"),
                            msg.content or "",
                        )
                    ],
                }
                others.append(d)
            else:
                content = list(self._build_content_parts(msg.content))
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        tool_names_by_id[tc.id] = tc.function.name
                        content.append(self._tool_call_block(tc))
                if not content:
                    content = self._wrap_content(None)
                d = {"role": msg.role, "content": content}
                if msg.name:
                    d["name"] = msg.name
                others.append(d)
        return system_prompt, others

    def _build_body(self, req: ChatCompletionRequest, system_prompt: str | None, messages: list) -> dict:
        params: dict[str, Any] = {
            "model": resolve_model_id(req.model),
            "messages": messages,
            "max_tokens": req.max_tokens or 64000,
            "stream": req.stream,
        }
        if system_prompt:
            params["system"] = system_prompt
        if req.temperature is not None:
            params["temperature"] = req.temperature
        if req.reasoning_effort is not None:
            model_id = resolve_model_id(req.model)
            effort = clamp_reasoning_effort(model_id, req.reasoning_effort)
            if effort:
                params["reasoning_effort"] = effort
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
        return make_cc_body(config=make_config(), params=params)

    def _build_headers(self) -> dict[str, str]:
        return make_cc_headers()
