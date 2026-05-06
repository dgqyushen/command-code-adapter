from __future__ import annotations

import json
import logging
import uuid
import time
from typing import AsyncGenerator

from cc_adapter.models.openai import ChatCompletionResponse, ChatCompletionChunk, ChatMessageResponse, Choice, DeltaChoice, ToolCall, FunctionCall, Usage
from cc_adapter.errors import AdapterError

logger = logging.getLogger(__name__)

FINISH_REASON_MAP = {
    "end_turn": "stop",
    "tool_calls": "tool_calls",
}


def _generate_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex[:12]}"


def _now() -> int:
    return int(time.time())


def _map_finish_reason(cc_reason: str | None) -> str | None:
    if cc_reason is None:
        return None
    return FINISH_REASON_MAP.get(cc_reason, "stop")


def _make_tool_call(cc_event: dict, index: int = 0) -> ToolCall:
    return ToolCall(
        id=cc_event.get("toolCallId", f"call_{uuid.uuid4().hex[:8]}"),
        function=FunctionCall(
            name=cc_event.get("toolName", ""),
            arguments=json.dumps(cc_event.get("args", {})),
        ),
    )


async def translate_stream(cc_stream: AsyncGenerator[dict, None], model: str) -> AsyncGenerator[str, None]:
    """Translate CC SSE events into OpenAI SSE chunks on the fly."""
    response_id = _generate_id()
    created = _now()
    tool_call_index = 0
    usage = None

    try:
        async for event in cc_stream:
            event_type = event.get("type")

            if event_type == "text-delta":
                chunk = ChatCompletionChunk(
                    id=response_id,
                    created=created,
                    model=model,
                    choices=[DeltaChoice(delta=ChatMessageResponse(content=event.get("text", "")))],
                )
                yield f"data: {chunk.model_dump_json(exclude_none=True)}\n\n"

            elif event_type == "reasoning-delta":
                logger.debug("Reasoning delta ignored: %s", event.get("text", "")[:50])

            elif event_type == "tool-call":
                tool_call = _make_tool_call(event, tool_call_index)
                chunk = ChatCompletionChunk(
                    id=response_id,
                    created=created,
                    model=model,
                    choices=[DeltaChoice(delta=ChatMessageResponse(tool_calls=[tool_call]))],
                )
                yield f"data: {chunk.model_dump_json(exclude_none=True)}\n\n"
                tool_call_index += 1

            elif event_type == "tool-result":
                pass  # OpenAI doesn't return tool results in chat completions

            elif event_type == "finish":
                finish_reason = _map_finish_reason(event.get("finishReason"))
                raw_usage = event.get("totalUsage")
                if raw_usage:
                    usage = Usage(
                        prompt_tokens=raw_usage.get("inputTokens", 0),
                        completion_tokens=raw_usage.get("outputTokens", 0),
                        total_tokens=raw_usage.get("inputTokens", 0) + raw_usage.get("outputTokens", 0),
                    )
                chunk = ChatCompletionChunk(
                    id=response_id,
                    created=created,
                    model=model,
                    choices=[DeltaChoice(delta=ChatMessageResponse(), finish_reason=finish_reason)],
                    usage=usage,
                )
                yield f"data: {chunk.model_dump_json(exclude_none=True)}\n\n"

            elif event_type == "error":
                err_data = event.get("error", {})
                logger.error("CC stream error: %s", err_data.get("message", "Unknown"))
                chunk = ChatCompletionChunk(
                    id=response_id,
                    created=created,
                    model=model,
                    choices=[DeltaChoice(delta=ChatMessageResponse(), finish_reason="stop")],
                )
                yield f"data: {chunk.model_dump_json(exclude_none=True)}\n\n"
    except AdapterError as e:
        logger.error("Stream error from CC API: %s", e.message)
        error_chunk = ChatCompletionChunk(
            id=response_id,
            created=created,
            model=model,
            choices=[DeltaChoice(delta=ChatMessageResponse(), finish_reason="stop")],
        )
        yield f"data: {error_chunk.model_dump_json(exclude_none=True)}\n\n"

    yield "data: [DONE]\n\n"


async def collect_and_translate_nonstream(cc_stream: AsyncGenerator[dict, None], model: str) -> ChatCompletionResponse:
    """Collect all CC SSE events and build a single ChatCompletionResponse."""
    response_id = _generate_id()
    created = _now()
    content_parts: list[str] = []
    tool_calls: list[ToolCall] = []
    finish_reason: str | None = None
    usage: Usage | None = None
    tool_call_index = 0

    async for event in cc_stream:
        event_type = event.get("type")

        if event_type == "text-delta":
            content_parts.append(event.get("text", ""))

        elif event_type == "tool-call":
            tool_calls.append(_make_tool_call(event, tool_call_index))
            tool_call_index += 1

        elif event_type == "finish":
            finish_reason = _map_finish_reason(event.get("finishReason"))
            raw_usage = event.get("totalUsage")
            if raw_usage:
                usage = Usage(
                    prompt_tokens=raw_usage.get("inputTokens", 0),
                    completion_tokens=raw_usage.get("outputTokens", 0),
                    total_tokens=raw_usage.get("inputTokens", 0) + raw_usage.get("outputTokens", 0),
                )

        elif event_type == "error":
            err_data = event.get("error", {})
            logger.error("CC stream error: %s", err_data.get("message", "Unknown"))
            finish_reason = "stop"

    content = "".join(content_parts) or None
    message = ChatMessageResponse(content=content, tool_calls=tool_calls or None)
    choice = Choice(message=message, finish_reason=finish_reason or "stop")

    return ChatCompletionResponse(
        id=response_id,
        created=created,
        model=model,
        choices=[choice],
        usage=usage,
    )
