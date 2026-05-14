from __future__ import annotations

import json
import time
import uuid
from typing import AsyncGenerator, Any

from cc_adapter.core.errors import AdapterError, map_upstream_error
from cc_adapter.providers.shared.tool_mapping import normalize_args


def _generate_id() -> str:
    return f"resp_{uuid.uuid4().hex[:12]}"


def _generate_msg_id() -> str:
    return f"msg_{uuid.uuid4().hex[:12]}"


def _generate_rs_id() -> str:
    return f"rs_{uuid.uuid4().hex[:12]}"


def _generate_fc_id() -> str:
    return f"fc_{uuid.uuid4().hex[:12]}"


def _sse(event_type: str, data: dict) -> str:
    payload = {"type": event_type, **data}
    return f"event: {event_type}\ndata: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


def _parse_usage(raw_usage: dict | None) -> dict | None:
    if not raw_usage:
        return None
    input_t = raw_usage.get("inputTokens", 0)
    output_t = raw_usage.get("outputTokens", 0)
    result = {
        "input_tokens": input_t,
        "output_tokens": output_t,
        "total_tokens": input_t + output_t,
    }
    reasoning_tokens = raw_usage.get("reasoningTokens")
    if reasoning_tokens:
        result["output_tokens_details"] = {"reasoning_tokens": reasoning_tokens}
    return result


async def translate_responses_stream(
    cc_stream: AsyncGenerator[dict, None],
    model: str,
) -> AsyncGenerator[str, None]:
    response_id = _generate_id()
    created = time.time()

    text_buf: list[str] = []
    reasoning_buf: list[str] = []
    text_item_id: str | None = None
    reasoning_item_id: str | None = None
    fc_item_ids: list[str] = []
    fc_call_ids: list[str] = []
    fc_names: list[str] = []
    fc_args: list[str] = []
    output_index = 0
    seq = 0
    has_any_output = False
    current_item_type: str | None = None
    current_item_id_val: str | None = None
    current_item_type_val: str | None = None

    def close_current_item():
        nonlocal output_index, seq, current_item_type, current_item_id_val
        if current_item_type == "reasoning":
            yield _sse(
                "response.content_part.done",
                {
                    "content_index": 0,
                    "item_id": current_item_id_val,
                    "output_index": output_index,
                    "part": {"type": "reasoning_text", "text": "".join(reasoning_buf)},
                    "sequence_number": seq,
                },
            )
            seq += 1
            yield _sse(
                "response.output_item.done",
                {
                    "output_index": output_index,
                    "item": {
                        "type": "reasoning",
                        "id": current_item_id_val,
                        "content": [{"type": "reasoning_text", "text": "".join(reasoning_buf)}],
                        "status": "completed",
                    },
                    "sequence_number": seq,
                },
            )
            seq += 1
            output_index += 1
        elif current_item_type == "text":
            yield _sse(
                "response.content_part.done",
                {
                    "content_index": 0,
                    "item_id": current_item_id_val,
                    "output_index": output_index,
                    "part": {"type": "output_text", "text": "".join(text_buf), "annotations": []},
                    "sequence_number": seq,
                },
            )
            seq += 1
            yield _sse(
                "response.output_text.done",
                {
                    "content_index": 0,
                    "item_id": current_item_id_val,
                    "output_index": output_index,
                    "text": "".join(text_buf),
                    "sequence_number": seq,
                },
            )
            seq += 1
            yield _sse(
                "response.output_item.done",
                {
                    "output_index": output_index,
                    "item": {
                        "type": "message",
                        "id": current_item_id_val,
                        "role": "assistant",
                        "status": "completed",
                        "content": [{"type": "output_text", "text": "".join(text_buf), "annotations": []}],
                    },
                    "sequence_number": seq,
                },
            )
            seq += 1
            output_index += 1
        elif current_item_type == "fc":
            output_index += 1
        current_item_type_val = None

    def set_current_item(item_type: str, item_id: str):
        nonlocal current_item_type, current_item_id_val, current_item_type_val
        current_item_type = item_type
        current_item_id_val = item_id
        current_item_type_val = item_type

    partial = {
        "id": response_id,
        "object": "response",
        "status": "in_progress",
        "created_at": created,
        "model": model,
        "output": [],
        "usage": None,
    }
    bootstrap_done = False

    def _emit_bootstrap():
        nonlocal bootstrap_done, seq
        if not bootstrap_done:
            bootstrap_done = True
            yield _sse("response.created", {"response": partial, "sequence_number": seq})
            seq += 1
            yield _sse("response.in_progress", {"response": partial, "sequence_number": seq})
            seq += 1

    async for event in cc_stream:
        event_type = event.get("type")

        if event_type == "reasoning-delta":
            text = event.get("text") or ""
            if not text:
                continue
            for chunk in _emit_bootstrap():
                yield chunk
            has_any_output = True
            if current_item_type_val != "reasoning":
                if current_item_type_val is not None:
                    for chunk in close_current_item():
                        yield chunk
                reasoning_item_id = _generate_rs_id()
                set_current_item("reasoning", reasoning_item_id)
                yield _sse(
                    "response.output_item.added",
                    {
                        "output_index": output_index,
                        "item": {"type": "reasoning", "id": reasoning_item_id, "content": [], "status": "in_progress"},
                        "sequence_number": seq,
                    },
                )
                seq += 1
                yield _sse(
                    "response.content_part.added",
                    {
                        "content_index": 0,
                        "item_id": reasoning_item_id,
                        "output_index": output_index,
                        "part": {"type": "reasoning_text", "text": ""},
                        "sequence_number": seq,
                    },
                )
                seq += 1
            reasoning_buf.append(text)
            yield _sse(
                "response.reasoning_text.delta",
                {
                    "delta": text,
                    "content_index": 0,
                    "item_id": current_item_id_val,
                    "output_index": output_index,
                    "sequence_number": seq,
                },
            )
            seq += 1

        elif event_type == "text-delta":
            text = event.get("text") or ""
            if not text:
                continue
            for chunk in _emit_bootstrap():
                yield chunk
            has_any_output = True
            if current_item_type_val != "text":
                if current_item_type_val is not None:
                    for chunk in close_current_item():
                        yield chunk
                text_item_id = _generate_msg_id()
                set_current_item("text", text_item_id)
                yield _sse(
                    "response.output_item.added",
                    {
                        "output_index": output_index,
                        "item": {
                            "type": "message",
                            "id": text_item_id,
                            "role": "assistant",
                            "status": "in_progress",
                            "content": [],
                        },
                        "sequence_number": seq,
                    },
                )
                seq += 1
                yield _sse(
                    "response.content_part.added",
                    {
                        "content_index": 0,
                        "item_id": text_item_id,
                        "output_index": output_index,
                        "part": {"type": "output_text", "text": "", "annotations": []},
                        "sequence_number": seq,
                    },
                )
                seq += 1
            text_buf.append(text)
            yield _sse(
                "response.output_text.delta",
                {
                    "delta": text,
                    "content_index": 0,
                    "item_id": current_item_id_val,
                    "output_index": output_index,
                    "sequence_number": seq,
                },
            )
            seq += 1

        elif event_type == "tool-call":
            for chunk in _emit_bootstrap():
                yield chunk
            has_any_output = True
            tool_name = event.get("toolName", "")
            tool_call_id = event.get("toolCallId", f"call_{uuid.uuid4().hex[:8]}")
            raw_args = event.get("input", {})
            args_str = json.dumps(normalize_args(tool_name, raw_args), ensure_ascii=False, separators=(",", ":"))

            if current_item_type_val is not None:
                for chunk in close_current_item():
                    yield chunk

            fc_id = _generate_fc_id()
            fc_item_ids.append(fc_id)
            fc_call_ids.append(tool_call_id)
            fc_names.append(tool_name)
            fc_args.append(args_str)
            set_current_item("fc", fc_id)

            yield _sse(
                "response.output_item.added",
                {
                    "output_index": output_index,
                    "item": {
                        "type": "function_call",
                        "id": fc_id,
                        "call_id": tool_call_id,
                        "name": tool_name,
                        "arguments": "",
                        "status": "in_progress",
                    },
                    "sequence_number": seq,
                },
            )
            seq += 1

            yield _sse(
                "response.function_call_arguments.delta",
                {
                    "delta": args_str,
                    "item_id": fc_id,
                    "output_index": output_index,
                    "sequence_number": seq,
                },
            )
            seq += 1

            yield _sse(
                "response.function_call_arguments.done",
                {
                    "arguments": args_str,
                    "item_id": fc_id,
                    "name": tool_name,
                    "output_index": output_index,
                    "sequence_number": seq,
                },
            )
            seq += 1

            yield _sse(
                "response.output_item.done",
                {
                    "output_index": output_index,
                    "item": {
                        "type": "function_call",
                        "id": fc_id,
                        "call_id": tool_call_id,
                        "name": tool_name,
                        "arguments": args_str,
                        "status": "completed",
                    },
                    "sequence_number": seq,
                },
            )
            seq += 1
            output_index += 1
            current_item_type = None
            current_item_id_val = None
            current_item_type_val = None

        elif event_type == "finish":
            if not has_any_output:
                raise AdapterError(message="Upstream model returned an empty response", status_code=502)

            if current_item_type_val is not None:
                for chunk in close_current_item():
                    yield chunk

            usage = _parse_usage(event.get("totalUsage"))
            full_text = "".join(text_buf)
            output_items: list[dict] = []
            if reasoning_buf:
                rs_id = reasoning_item_id or _generate_rs_id()
                output_items.append(
                    {
                        "type": "reasoning",
                        "id": rs_id,
                        "content": [{"type": "reasoning_text", "text": "".join(reasoning_buf)}],
                        "status": "completed",
                    }
                )
            if full_text:
                msg_id = text_item_id or _generate_msg_id()
                output_items.append(
                    {
                        "type": "message",
                        "id": msg_id,
                        "role": "assistant",
                        "status": "completed",
                        "content": [{"type": "output_text", "text": full_text, "annotations": []}],
                    }
                )
            for i, fc_id in enumerate(fc_item_ids):
                output_items.append(
                    {
                        "type": "function_call",
                        "id": fc_id,
                        "call_id": fc_call_ids[i] if i < len(fc_call_ids) else f"call_{uuid.uuid4().hex[:8]}",
                        "name": fc_names[i] if i < len(fc_names) else "",
                        "arguments": fc_args[i] if i < len(fc_args) else "{}",
                        "status": "completed",
                    }
                )

            yield _sse(
                "response.completed",
                {
                    "response": {
                        "id": response_id,
                        "object": "response",
                        "status": "completed",
                        "created_at": created,
                        "completed_at": time.time(),
                        "model": model,
                        "output": output_items,
                        "usage": usage,
                        "output_text": full_text,
                    },
                    "sequence_number": seq,
                },
            )
            return

        elif event_type == "error":
            err = event.get("error") or {}
            message = err.get("message", "Unknown error")
            yield _sse(
                "error",
                {
                    "code": str(err.get("statusCode", 502)),
                    "message": message,
                    "sequence_number": seq,
                },
            )
            return

    if not has_any_output:
        raise AdapterError(message="Upstream model returned an empty response", status_code=502)

    yield _sse(
        "error",
        {
            "message": "Upstream stream ended before finish",
            "sequence_number": seq,
        },
    )


async def collect_and_translate_responses_nonstream(
    cc_stream: AsyncGenerator[dict, None],
    model: str,
) -> dict:
    response_id = _generate_id()
    created = time.time()
    text_parts: list[str] = []
    reasoning_parts: list[str] = []
    tool_calls: list[dict] = []
    usage: dict | None = None

    async for event in cc_stream:
        event_type = event.get("type")

        if event_type == "text-delta":
            text_parts.append(event.get("text") or "")

        elif event_type == "reasoning-delta":
            reasoning_parts.append(event.get("text") or "")

        elif event_type == "tool-call":
            tool_name = event.get("toolName", "")
            raw_args = event.get("input", {})
            tc = {
                "type": "function_call",
                "id": _generate_fc_id(),
                "call_id": event.get("toolCallId", f"call_{uuid.uuid4().hex[:8]}"),
                "name": tool_name,
                "arguments": json.dumps(normalize_args(tool_name, raw_args), ensure_ascii=False),
                "status": "completed",
            }
            tool_calls.append(tc)

        elif event_type == "finish":
            usage = _parse_usage(event.get("totalUsage"))

        elif event_type == "error":
            err = event.get("error") or {}
            raise map_upstream_error(
                err.get("statusCode", 502),
                err.get("message", "Unknown CC error"),
            )

    text = "".join(text_parts)
    has_visible_output = bool(text) or bool(reasoning_parts) or bool(tool_calls)
    if not has_visible_output:
        raise AdapterError(message="Upstream model returned an empty response", status_code=502)

    output_items: list[dict] = []

    if reasoning_parts:
        output_items.append(
            {
                "type": "reasoning",
                "id": _generate_rs_id(),
                "content": [{"type": "reasoning_text", "text": "".join(reasoning_parts)}],
                "status": "completed",
            }
        )

    if text:
        output_items.append(
            {
                "type": "message",
                "id": _generate_msg_id(),
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": text, "annotations": []}],
            }
        )

    output_items.extend(tool_calls)

    return {
        "id": response_id,
        "object": "response",
        "status": "completed",
        "created_at": created,
        "completed_at": time.time(),
        "model": model,
        "output": output_items,
        "usage": usage,
        "output_text": text,
    }
