from __future__ import annotations

import json
import logging
import time
import uuid
from typing import AsyncGenerator

from cc_adapter.anthropic.models import AnthropicResponse, AnthropicUsage
from cc_adapter.errors import AdapterError, map_upstream_error
from cc_adapter.translator.tool_mapping import normalize_args

logger = logging.getLogger(__name__)

_STOP_REASON_MAP = {
    "end_turn": "end_turn",
    "tool_calls": "tool_use",
}


def _map_stop_reason(cc_reason: str | None) -> str | None:
    if cc_reason is None:
        return None
    return _STOP_REASON_MAP.get(cc_reason, "end_turn")


def _generate_id() -> str:
    return f"msg_{uuid.uuid4().hex[:16]}"


async def collect_and_translate_anthropic_nonstream(
    cc_stream: AsyncGenerator[dict, None],
    model: str,
) -> AnthropicResponse:
    response_id = _generate_id()
    thinking_parts: list[str] = []
    text_parts: list[str] = []
    tool_calls: list[dict] = []
    finish_reason: str | None = None
    usage = AnthropicUsage()

    async for event in cc_stream:
        event_type = event.get("type")

        if event_type == "text-delta":
            text_parts.append(event.get("text", ""))

        elif event_type == "reasoning-delta":
            thinking_parts.append(event.get("text", ""))

        elif event_type == "tool-call":
            tc = {
                "type": "tool_use",
                "id": event.get("toolCallId", f"toolu_{uuid.uuid4().hex[:12]}"),
                "name": event.get("toolName", ""),
                "input": normalize_args(event.get("toolName", ""), event.get("input", {})),
            }
            tool_calls.append(tc)

        elif event_type == "finish":
            finish_reason = event.get("finishReason")
            raw_usage = event.get("totalUsage") or {}
            usage = AnthropicUsage(
                input_tokens=raw_usage.get("inputTokens", 0),
                output_tokens=raw_usage.get("outputTokens", 0),
            )

        elif event_type == "error":
            err = event.get("error", {})
            raise map_upstream_error(
                err.get("statusCode", 502),
                err.get("message", "Unknown CC error"),
            )

    content_blocks: list[dict] = []
    has_thinking = bool(thinking_parts)
    has_text = bool(text_parts)
    has_tool_calls = bool(tool_calls)

    if not has_text and not has_tool_calls:
        if has_thinking:
            content_blocks.append({"type": "text", "text": "".join(thinking_parts)})
        else:
            raise AdapterError(message="Upstream model returned an empty response", status_code=502)
    else:
        if has_thinking:
            content_blocks.append({"type": "thinking", "thinking": "".join(thinking_parts)})
        if has_text:
            content_blocks.append({"type": "text", "text": "".join(text_parts)})
        content_blocks.extend(tool_calls)

    stop_reason = _map_stop_reason(finish_reason)
    if tool_calls:
        stop_reason = "tool_use"

    return AnthropicResponse(
        id=response_id,
        content=content_blocks,
        model=model,
        stop_reason=stop_reason,
        usage=usage,
    )
