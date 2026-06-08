from __future__ import annotations

import structlog
from typing import Any

from cc_adapter.providers.anthropic.models import AnthropicRequest, extract_system_text, normalize_system_messages
from cc_adapter.command_code.headers import make_cc_headers
from cc_adapter.providers.shared.model_mapping import resolve_model_id, clamp_reasoning_effort
from cc_adapter.providers.shared.tool_mapping import make_tool_call_block, make_tool_result_block, normalize_schema
from cc_adapter.command_code.body import make_config, make_cc_body
from cc_adapter.core.errors import AdapterError

logger = structlog.get_logger(__name__)

_NOT_SUPPORTED = {"top_p", "top_k", "stop_sequences"}


def _budget_to_effort(budget: int | None) -> str | None:
    if budget is None:
        return None
    if budget < 4000:
        return "low"
    if budget < 8000:
        return "medium"
    if budget < 16000:
        return "high"
    return "xhigh"


class AnthropicTranslator:
    def translate(self, req: AnthropicRequest) -> tuple[dict[str, Any], dict[str, Any]]:
        req = normalize_system_messages(req)
        self._warn_unsupported(req)
        cc_body = self._build_body(req)
        cc_headers = make_cc_headers()
        return cc_body, cc_headers

    def _warn_unsupported(self, req: AnthropicRequest) -> None:
        for param in _NOT_SUPPORTED:
            value = getattr(req, param, None)
            if value is not None:
                logger.warning("Unsupported Anthropic parameter ignored: %s = %s", param, value)

    def _build_body(self, req: AnthropicRequest) -> dict[str, Any]:
        params: dict[str, Any] = {
            "model": resolve_model_id(req.model),
            "messages": self._build_messages(req.messages),
            "max_tokens": req.max_tokens,
            "stream": True,
        }

        system_text = extract_system_text(req.system)
        if system_text:
            params["system"] = system_text

        if req.tools:
            params["tools"] = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": normalize_schema(self._require_tool_schema(t)),
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
            effort = _budget_to_effort(req.thinking.budget_tokens)
            if effort:
                clamped = clamp_reasoning_effort(resolve_model_id(req.model), effort)
                if clamped:
                    params["reasoning_effort"] = clamped

        if req.temperature is not None:
            params["temperature"] = req.temperature

        return make_cc_body(config=make_config(), params=params)

    def _require_tool_schema(self, tool: Any) -> dict[str, Any]:
        if tool.input_schema is not None:
            return tool.input_schema
        if tool.type:
            raise AdapterError(
                message=(
                    f"Anthropic server tool '{tool.name}' cannot be translated to Command Code; "
                    "enable DeepSeek web_search forwarding for server-side tools"
                ),
                status_code=400,
            )
        raise AdapterError(message=f"Anthropic tool '{tool.name}' must include input_schema", status_code=400)

    def _build_messages(self, messages: list[Any]) -> list[dict[str, Any]]:
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
                    make_tool_call_block(
                        block.get("id", ""),
                        block.get("name", ""),
                        block.get("input", {}),
                    )
                )
            elif block_type == "tool_result":
                raw_content = block.get("content", "")
                if isinstance(raw_content, list):
                    raw_content = " ".join(
                        b.get("text", "") for b in raw_content if isinstance(b, dict) and b.get("type") == "text"
                    )
                result.append(
                    make_tool_result_block(
                        block.get("tool_use_id", ""),
                        "",
                        raw_content,
                    )
                )
            elif block_type == "image":
                logger.warning("Image content block not supported, skipping")
            elif block_type == "thinking":
                pass
        return result
