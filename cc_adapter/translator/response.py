from __future__ import annotations

import json
import logging
import uuid
import time
from typing import AsyncGenerator

from cc_adapter.models.openai import (
    ChatCompletionResponse,
    ChatCompletionChunk,
    ChatMessageResponse,
    Choice,
    DeltaChoice,
    ToolCall,
    FunctionCall,
    Usage,
)
from cc_adapter.errors import AdapterError
from cc_adapter.translator.tool_mapping import normalize_args

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


def _make_tool_call(cc_event: dict, index: int = 0, include_index: bool = False) -> ToolCall:
    tool_name = cc_event.get("toolName", "")
    raw_args = cc_event.get("input", cc_event.get("args", {}))
    args = normalize_args(tool_name, raw_args)
    return ToolCall(
        index=index if include_index else None,
        id=cc_event.get("toolCallId", f"call_{uuid.uuid4().hex[:8]}"),
        function=FunctionCall(
            name=cc_event.get("toolName", ""),
            arguments=json.dumps(args),
        ),
    )


async def translate_stream(
    cc_stream: AsyncGenerator[dict, None], model: str, start_time: float
) -> AsyncGenerator[str, None]:
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
                chunk = ChatCompletionChunk(
                    id=response_id,
                    created=created,
                    model=model,
                    choices=[DeltaChoice(delta=ChatMessageResponse(reasoning_content=event.get("text", "")))],
                )
                yield f"data: {chunk.model_dump_json(exclude_none=True)}\n\n"

            elif event_type == "tool-call":
                logger.info("CC tool-call event: %s", event)
                tool_call = _make_tool_call(event, tool_call_index, include_index=True)
                logger.info(
                    "Translated tool-call: id=%s name=%s args=%s",
                    tool_call.id,
                    tool_call.function.name,
                    tool_call.function.arguments,
                )
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
                finish_reason = "tool_calls" if tool_call_index else _map_finish_reason(event.get("finishReason"))
                raw_usage = event.get("totalUsage")
                if raw_usage:
                    usage = Usage(
                        prompt_tokens=raw_usage.get("inputTokens", 0),
                        completion_tokens=raw_usage.get("outputTokens", 0),
                        total_tokens=raw_usage.get("inputTokens", 0) + raw_usage.get("outputTokens", 0),
                    )
                    elapsed = time.time() - start_time
                    logger.info(
                        "Usage: model=%s input=%d output=%d total=%d elapsed=%.1fs",
                        model,
                        usage.prompt_tokens,
                        usage.completion_tokens,
                        usage.total_tokens,
                        elapsed,
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


async def collect_and_translate_nonstream(
    cc_stream: AsyncGenerator[dict, None], model: str, start_time: float
) -> ChatCompletionResponse:
    """Collect all CC SSE events and build a single ChatCompletionResponse."""
    response_id = _generate_id()
    created = _now()
    content_parts: list[str] = []
    reasoning_parts: list[str] = []
    tool_calls: list[ToolCall] = []
    finish_reason: str | None = None
    usage: Usage | None = None
    tool_call_index = 0

    async for event in cc_stream:
        event_type = event.get("type")

        if event_type == "text-delta":
            content_parts.append(event.get("text", ""))

        elif event_type == "reasoning-delta":
            reasoning_parts.append(event.get("text", ""))

        elif event_type == "tool-call":
            logger.info("CC tool-call event (nonstream): %s", event)
            tc = _make_tool_call(event, tool_call_index)
            logger.info(
                "Translated tool-call (nonstream): id=%s name=%s args=%s",
                tc.id,
                tc.function.name,
                tc.function.arguments,
            )
            tool_calls.append(tc)
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
                elapsed = time.time() - start_time
                logger.info(
                    "Usage: model=%s input=%d output=%d total=%d elapsed=%.1fs",
                    model,
                    usage.prompt_tokens,
                    usage.completion_tokens,
                    usage.total_tokens,
                    elapsed,
                )

        elif event_type == "error":
            err_data = event.get("error", {})
            logger.error("CC stream error: %s", err_data.get("message", "Unknown"))
            finish_reason = "stop"

    content = "".join(content_parts) or None
    reasoning_content = "".join(reasoning_parts) or None
    message = ChatMessageResponse(content=content, reasoning_content=reasoning_content, tool_calls=tool_calls or None)
    choice = Choice(message=message, finish_reason=finish_reason or "stop")

    return ChatCompletionResponse(
        id=response_id,
        created=created,
        model=model,
        choices=[choice],
        usage=usage,
    )
