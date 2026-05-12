from __future__ import annotations

import copy
import datetime
import logging
from typing import Any

from cc_adapter.anthropic.models import AnthropicRequest
from cc_adapter.headers import make_cc_headers
from cc_adapter._shared import MODEL_PROVIDER_MAP
from cc_adapter._tool_mapping import normalize_input_args, normalize_schema

logger = logging.getLogger(__name__)

_NOT_SUPPORTED = {"top_p", "top_k", "stop_sequences"}

_CC_BODY_SKELETON: dict[str, Any] = {
    "memory": "",
    "taste": None,
    "skills": None,
    "permissionMode": "standard",
}


_STATIC_CONFIG = {
    "env": "adapter",
    "workingDir": "/home/user/project",
    "environment": "production",
    "structure": ["src/", "tests/", "docs/"],
    "isGitRepo": True,
    "currentBranch": "main",
    "mainBranch": "main",
    "gitStatus": "clean",
    "recentCommits": [],
}


def _make_config() -> dict[str, Any]:
    base = copy.deepcopy(_STATIC_CONFIG)
    base["date"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    return base


def _make_cc_body(params: dict[str, Any]) -> dict[str, Any]:
    return {**_CC_BODY_SKELETON, "config": _make_config(), "params": params}


def _budget_to_effort(budget: int | None) -> str:
    if budget is None:
        return "high"
    if budget < 4000:
        return "low"
    if budget < 8000:
        return "medium"
    if budget < 16000:
        return "high"
    return "xhigh"


def _extract_system_text(system: str | list[dict[str, Any]] | None) -> str | None:
    if system is None:
        return None
    if isinstance(system, str):
        return system
    texts = [b.get("text", "") for b in system if isinstance(b, dict) and b.get("type") == "text"]
    return " ".join(texts) if texts else None


class AnthropicTranslator:
    def translate(self, req: AnthropicRequest) -> tuple[dict[str, Any], dict[str, Any]]:
        self._warn_unsupported(req)
        cc_body = self._build_body(req)
        cc_headers = make_cc_headers()
        return cc_body, cc_headers

    def _warn_unsupported(self, req: AnthropicRequest) -> None:
        for param in _NOT_SUPPORTED:
            value = getattr(req, param, None)
            if value is not None:
                logger.warning("Unsupported Anthropic parameter ignored: %s = %s", param, value)

    @staticmethod
    def _normalize_model(model: str) -> str:
        return MODEL_PROVIDER_MAP.get(model, model)

    def _build_body(self, req: AnthropicRequest) -> dict[str, Any]:
        params: dict[str, Any] = {
            "model": self._normalize_model(req.model),
            "messages": self._build_messages(req.messages),
            "max_tokens": req.max_tokens,
            "stream": True,
        }

        system_text = _extract_system_text(req.system)
        if system_text:
            params["system"] = system_text

        if req.tools:
            params["tools"] = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": normalize_schema(t.input_schema),
                }
                for t in req.tools
            ]

        if req.tool_choice:
            tc = req.tool_choice
            choice: dict[str, Any] = {"type": tc.type}
            if tc.name:
                choice["name"] = tc.name
            params["tool_choice"] = choice

        if req.thinking and req.thinking.type in ("enabled", "adaptive"):
            params["reasoning_effort"] = _budget_to_effort(req.thinking.budget_tokens)

        if req.temperature is not None:
            params["temperature"] = req.temperature

        return _make_cc_body(params)

    def _build_messages(self, messages) -> list[dict[str, Any]]:
        tool_names: dict[str, str] = {}
        for msg in messages:
            if isinstance(msg.content, list):
                for block in msg.content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tool_names[block.get("id", "")] = block.get("name", "")
        result = []
        for msg in messages:
            if isinstance(msg.content, str):
                result.append({"role": msg.role, "content": [{"type": "text", "text": msg.content}]})
            else:
                blocks = self._translate_content_blocks(msg.content)
                tool_results = [b for b in blocks if b["type"] == "tool-result"]
                other_blocks = [b for b in blocks if b["type"] != "tool-result"]
                if other_blocks:
                    result.append({"role": msg.role, "content": other_blocks})
                for tr in tool_results:
                    tr["toolName"] = tool_names.get(tr.get("toolCallId", ""), "unknown")
                    result.append({"role": "tool", "content": [tr]})
        return result

    def _translate_content_blocks(self, blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result = []
        for block in blocks:
            block_type = block.get("type", "text")
            if block_type == "text":
                result.append({"type": "text", "text": block.get("text", "")})
            elif block_type == "tool_use":
                result.append(
                    {
                        "type": "tool-call",
                        "toolCallId": block.get("id", ""),
                        "toolName": block.get("name", ""),
                        "input": normalize_input_args(block.get("input", {})),
                    }
                )
            elif block_type == "tool_result":
                raw_content = block.get("content", "")
                if isinstance(raw_content, list):
                    raw_content = " ".join(
                        b.get("text", "") for b in raw_content if isinstance(b, dict) and b.get("type") == "text"
                    )
                result.append(
                    {
                        "type": "tool-result",
                        "toolCallId": block.get("tool_use_id", ""),
                        "output": {"type": "text", "value": raw_content},
                    }
                )
            elif block_type == "image":
                logger.warning("Image content block not supported, skipping")
            elif block_type == "thinking":
                pass
        return result
