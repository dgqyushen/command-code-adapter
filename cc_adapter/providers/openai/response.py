from __future__ import annotations

import json
import uuid
import time
from typing import AsyncGenerator

import structlog

from cc_adapter.providers.openai.models import (
    ChatCompletionResponse,
    ChatCompletionChunk,
    ChatMessageResponse,
    Choice,
    DeltaChoice,
    ToolCall,
    FunctionCall,
    Usage,
)
from cc_adapter.core.errors import AdapterError, map_upstream_error
from cc_adapter.providers.shared.tool_mapping import normalize_args

logger = structlog.get_logger(__name__)

FINISH_REASON_MAP = {
    "end_turn": "stop",
    "tool_calls": "tool_calls",
}


def _generate_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex[:12]}"


def _now() -> int:
    return int(time.time())


def _stream_chunk_json(
    response_id: str,
    created: int,
    model: str,
    delta: dict,
    finish_reason: str | None = None,
    usage: dict | None = None,
) -> str:
    chunk: dict = {
        "id": response_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": delta,
            }
        ],
    }
    if finish_reason is not None:
        chunk["choices"][0]["finish_reason"] = finish_reason
    if usage is not None:
        chunk["usage"] = usage
    return json.dumps(chunk, ensure_ascii=False, default=str, separators=(",", ":"))


def _map_finish_reason(cc_reason: str | None) -> str | None:
    if cc_reason is None:
        return None
    return FINISH_REASON_MAP.get(cc_reason, cc_reason)


def _parse_usage(raw_usage: dict | None, model: str, start_time: float) -> Usage | None:
    if not raw_usage:
        return None
    usage = Usage(
        prompt_tokens=raw_usage.get("inputTokens", 0),
        completion_tokens=raw_usage.get("outputTokens", 0),
        total_tokens=raw_usage.get("inputTokens", 0) + raw_usage.get("outputTokens", 0),
    )
    elapsed = time.time() - start_time
    logger.info(
        "upstream.usage",
        model=model,
        input=usage.prompt_tokens,
        output=usage.completion_tokens,
        total=usage.total_tokens,
        elapsed=f"{elapsed:.1f}s",
    )
    return usage


def _stream_error_payload(error: AdapterError) -> dict:
    return error.to_openai_error()


def _event_error(event: dict) -> AdapterError:
    err_data = event.get("error") or {}
    message = err_data.get("message") or "Unknown error"
    status_code = err_data.get("statusCode") or 502
    logger.warning("upstream.error", error=message)
    return map_upstream_error(status_code, message)


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
    cc_stream: AsyncGenerator[dict, None],
    model: str,
    start_time: float,
    reasoning_effort: str | None = None,
    tools_available: bool = False,
) -> AsyncGenerator[str, None]:
    """Translate CC SSE events into OpenAI SSE chunks on the fly."""
    response_id = _generate_id()
    created = _now()
    tool_call_index = 0
    usage = None
    emitted_visible = False  # text-delta or tool-call seen
    reasoning_buf: list[str] = []  # buffered reasoning for fallback

    try:
        async for event in cc_stream:
            event_type = event.get("type")

            if event_type == "text-delta":
                text = event.get("text") or ""
                if not text:
                    continue
                emitted_visible = True
                yield f"data: {_stream_chunk_json(response_id, created, model, {'content': text, 'role': 'assistant'})}\n\n"

            elif event_type == "reasoning-delta":
                if reasoning_effort == "off":
                    continue
                text = event.get("text") or ""
                if not text:
                    continue
                reasoning_buf.append(text)
                yield f"data: {_stream_chunk_json(response_id, created, model, {'reasoning_content': text, 'role': 'assistant'})}\n\n"

            elif event_type == "tool-call":
                emitted_visible = True
                logger.debug(
                    "tool.call.debug", tool_name=event.get("toolName", ""), tool_call_id=event.get("toolCallId", "")
                )
                tool_call = _make_tool_call(event, tool_call_index, include_index=True)
                logger.info(
                    "tool.call",
                    tool_id=tool_call.id,
                    tool_name=tool_call.function.name,
                )
                tc_dict = {
                    "index": tool_call.index,
                    "id": tool_call.id,
                    "type": "function",
                    "function": {"name": tool_call.function.name, "arguments": tool_call.function.arguments},
                }
                yield f"data: {_stream_chunk_json(response_id, created, model, {'tool_calls': [tc_dict], 'role': 'assistant'})}\n\n"
                tool_call_index += 1

            elif event_type == "tool-result":
                pass  # OpenAI doesn't return tool results in chat completions

            elif event_type == "finish":
                if not emitted_visible:
                    if reasoning_buf and not tools_available:
                        fallback = "".join(reasoning_buf)
                        yield f"data: {_stream_chunk_json(response_id, created, model, {'content': fallback, 'role': 'assistant'})}\n\n"
                        emitted_visible = True
                    else:
                        error = AdapterError(message="Upstream model returned an empty response", status_code=502)
                        yield f"data: {json.dumps(_stream_error_payload(error))}\n\n"
                        break
                finish_reason = "tool_calls" if tool_call_index else _map_finish_reason(event.get("finishReason"))
                usage = _parse_usage(event.get("totalUsage"), model, start_time)
                usage_dict = usage.model_dump(exclude_none=True) if usage else None
                yield f"data: {_stream_chunk_json(response_id, created, model, {'role': 'assistant'}, finish_reason=finish_reason, usage=usage_dict)}\n\n"

            elif event_type == "error":
                error = _event_error(event)
                yield f"data: {json.dumps(_stream_error_payload(error))}\n\n"
                break
    except AdapterError as e:
        logger.warning("upstream.error", error=e.message)
        yield f"data: {json.dumps(_stream_error_payload(e))}\n\n"

    yield "data: [DONE]\n\n"


async def collect_and_translate_nonstream(
    cc_stream: AsyncGenerator[dict, None],
    model: str,
    start_time: float,
    reasoning_effort: str | None = None,
    tools_available: bool = False,
) -> ChatCompletionResponse:
    """Collect all CC SSE events and build a single ChatCompletionResponse."""
    response_id = _generate_id()
    created = _now()
    content_parts: list[str] = []
    reasoning_parts: list[str] = []
    tool_calls: list[ToolCall] = []
    finish_reason_raw: str | None = None
    usage: Usage | None = None
    tool_call_index = 0

    async for event in cc_stream:
        event_type = event.get("type")

        if event_type == "text-delta":
            content_parts.append(event.get("text") or "")

        elif event_type == "reasoning-delta":
            reasoning_parts.append(event.get("text") or "")

        elif event_type == "tool-call":
            logger.debug(
                "tool.call.debug", tool_name=event.get("toolName", ""), tool_call_id=event.get("toolCallId", "")
            )
            tc = _make_tool_call(event, tool_call_index)
            logger.info(
                "tool.call",
                tool_id=tc.id,
                tool_name=tc.function.name,
            )
            tool_calls.append(tc)
            tool_call_index += 1

        elif event_type == "finish":
            finish_reason_raw = event.get("finishReason")
            usage = _parse_usage(event.get("totalUsage"), model, start_time)

        elif event_type == "error":
            raise _event_error(event)

    content = "".join(content_parts) or None
    reasoning_content = None if reasoning_effort == "off" else ("".join(reasoning_parts) or None)

    # Empty response: no visible content AND no tool_calls AND no reasoning
    has_visible_output = bool(content) or bool(tool_calls)
    if not has_visible_output:
        if reasoning_content and not tools_available:
            content = reasoning_content
            reasoning_content = None
        else:
            raise AdapterError(message="Upstream model returned an empty response", status_code=502)

    # If tool calls were made, finish_reason is always tool_calls
    if tool_calls:
        finish_reason = "tool_calls"
    else:
        finish_reason = _map_finish_reason(finish_reason_raw) or "stop"

    message = ChatMessageResponse(content=content, reasoning_content=reasoning_content, tool_calls=tool_calls or None)
    choice = Choice(message=message, finish_reason=finish_reason)

    return ChatCompletionResponse(
        id=response_id,
        created=created,
        model=model,
        choices=[choice],
        usage=usage,
    )
