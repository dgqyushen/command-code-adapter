from __future__ import annotations

import json
import time
from typing import AsyncGenerator, Any

from cc_adapter.core.errors import AdapterError, map_upstream_error
from cc_adapter.core.utils import format_sse, generate_id, parse_usage
from cc_adapter.providers.shared.tool_mapping import normalize_args


def _sse(event_type: str, data: dict) -> str:
    payload = {"type": event_type, **data}
    return format_sse(event_type, payload)


class _ResponsesStreamState:
    def __init__(self, response_id: str, model: str, created: float):
        self.response_id = response_id
        self.model = model
        self.created = created

        self.text_buf: list[str] = []
        self.reasoning_buf: list[str] = []
        self.text_item_id: str | None = None
        self.reasoning_item_id: str | None = None
        self.fc_item_ids: list[str] = []
        self.fc_call_ids: list[str] = []
        self.fc_names: list[str] = []
        self.fc_args: list[str] = []
        self.output_index = 0
        self.seq = 0
        self.has_any_output = False
        self.current_item_type: str | None = None
        self.current_item_id: str | None = None
        self.bootstrap_done = False

        self.partial = {
            "id": response_id,
            "object": "response",
            "status": "in_progress",
            "created_at": created,
            "model": model,
            "output": [],
            "usage": None,
        }

    def close_current_item(self):
        if self.current_item_type == "reasoning":
            yield _sse(
                "response.content_part.done",
                {
                    "content_index": 0,
                    "item_id": self.current_item_id,
                    "output_index": self.output_index,
                    "part": {"type": "reasoning_text", "text": "".join(self.reasoning_buf)},
                    "sequence_number": self.seq,
                },
            )
            self.seq += 1
            yield _sse(
                "response.output_item.done",
                {
                    "output_index": self.output_index,
                    "item": {
                        "type": "reasoning",
                        "id": self.current_item_id,
                        "content": [{"type": "reasoning_text", "text": "".join(self.reasoning_buf)}],
                        "status": "completed",
                    },
                    "sequence_number": self.seq,
                },
            )
            self.seq += 1
            self.output_index += 1
        elif self.current_item_type == "text":
            yield _sse(
                "response.content_part.done",
                {
                    "content_index": 0,
                    "item_id": self.current_item_id,
                    "output_index": self.output_index,
                    "part": {"type": "output_text", "text": "".join(self.text_buf), "annotations": []},
                    "sequence_number": self.seq,
                },
            )
            self.seq += 1
            yield _sse(
                "response.output_text.done",
                {
                    "content_index": 0,
                    "item_id": self.current_item_id,
                    "output_index": self.output_index,
                    "text": "".join(self.text_buf),
                    "sequence_number": self.seq,
                },
            )
            self.seq += 1
            yield _sse(
                "response.output_item.done",
                {
                    "output_index": self.output_index,
                    "item": {
                        "type": "message",
                        "id": self.current_item_id,
                        "role": "assistant",
                        "status": "completed",
                        "content": [{"type": "output_text", "text": "".join(self.text_buf), "annotations": []}],
                    },
                    "sequence_number": self.seq,
                },
            )
            self.seq += 1
            self.output_index += 1
        elif self.current_item_type == "fc":
            self.output_index += 1
        self.current_item_type = None
        self.current_item_id = None

    def set_current_item(self, item_type: str, item_id: str):
        self.current_item_type = item_type
        self.current_item_id = item_id

    def emit_bootstrap(self):
        if not self.bootstrap_done:
            self.bootstrap_done = True
            yield _sse("response.created", {"response": self.partial, "sequence_number": self.seq})
            self.seq += 1
            yield _sse("response.in_progress", {"response": self.partial, "sequence_number": self.seq})
            self.seq += 1

    def process_event(self, event: dict):
        event_type = event.get("type")

        if event_type == "reasoning-delta":
            text = event.get("text") or ""
            if not text:
                return
            yield from self.emit_bootstrap()
            self.has_any_output = True
            if self.current_item_type != "reasoning":
                if self.current_item_type is not None:
                    yield from self.close_current_item()
                self.reasoning_item_id = generate_id("rs_")
                self.set_current_item("reasoning", self.reasoning_item_id)
                yield _sse(
                    "response.output_item.added",
                    {
                        "output_index": self.output_index,
                        "item": {
                            "type": "reasoning",
                            "id": self.reasoning_item_id,
                            "content": [],
                            "status": "in_progress",
                        },
                        "sequence_number": self.seq,
                    },
                )
                self.seq += 1
                yield _sse(
                    "response.content_part.added",
                    {
                        "content_index": 0,
                        "item_id": self.reasoning_item_id,
                        "output_index": self.output_index,
                        "part": {"type": "reasoning_text", "text": ""},
                        "sequence_number": self.seq,
                    },
                )
                self.seq += 1
            self.reasoning_buf.append(text)
            yield _sse(
                "response.reasoning_text.delta",
                {
                    "delta": text,
                    "content_index": 0,
                    "item_id": self.current_item_id,
                    "output_index": self.output_index,
                    "sequence_number": self.seq,
                },
            )
            self.seq += 1

        elif event_type == "text-delta":
            text = event.get("text") or ""
            if not text:
                return
            yield from self.emit_bootstrap()
            self.has_any_output = True
            if self.current_item_type != "text":
                if self.current_item_type is not None:
                    yield from self.close_current_item()
                self.text_item_id = generate_id("msg_")
                self.set_current_item("text", self.text_item_id)
                yield _sse(
                    "response.output_item.added",
                    {
                        "output_index": self.output_index,
                        "item": {
                            "type": "message",
                            "id": self.text_item_id,
                            "role": "assistant",
                            "status": "in_progress",
                            "content": [],
                        },
                        "sequence_number": self.seq,
                    },
                )
                self.seq += 1
                yield _sse(
                    "response.content_part.added",
                    {
                        "content_index": 0,
                        "item_id": self.text_item_id,
                        "output_index": self.output_index,
                        "part": {"type": "output_text", "text": "", "annotations": []},
                        "sequence_number": self.seq,
                    },
                )
                self.seq += 1
            self.text_buf.append(text)
            yield _sse(
                "response.output_text.delta",
                {
                    "delta": text,
                    "content_index": 0,
                    "item_id": self.current_item_id,
                    "output_index": self.output_index,
                    "sequence_number": self.seq,
                },
            )
            self.seq += 1

        elif event_type == "tool-call":
            yield from self.emit_bootstrap()
            self.has_any_output = True
            tool_name = event.get("toolName", "")
            tool_call_id = event.get("toolCallId", generate_id("call_", 8))
            raw_args = event.get("input", {})
            args_str = json.dumps(normalize_args(tool_name, raw_args), ensure_ascii=False, separators=(",", ":"))

            if self.current_item_type is not None:
                yield from self.close_current_item()

            fc_id = generate_id("fc_")
            self.fc_item_ids.append(fc_id)
            self.fc_call_ids.append(tool_call_id)
            self.fc_names.append(tool_name)
            self.fc_args.append(args_str)
            self.set_current_item("fc", fc_id)

            yield _sse(
                "response.output_item.added",
                {
                    "output_index": self.output_index,
                    "item": {
                        "type": "function_call",
                        "id": fc_id,
                        "call_id": tool_call_id,
                        "name": tool_name,
                        "arguments": "",
                        "status": "in_progress",
                    },
                    "sequence_number": self.seq,
                },
            )
            self.seq += 1

            yield _sse(
                "response.function_call_arguments.delta",
                {
                    "delta": args_str,
                    "item_id": fc_id,
                    "output_index": self.output_index,
                    "sequence_number": self.seq,
                },
            )
            self.seq += 1

            yield _sse(
                "response.function_call_arguments.done",
                {
                    "arguments": args_str,
                    "item_id": fc_id,
                    "name": tool_name,
                    "output_index": self.output_index,
                    "sequence_number": self.seq,
                },
            )
            self.seq += 1

            yield _sse(
                "response.output_item.done",
                {
                    "output_index": self.output_index,
                    "item": {
                        "type": "function_call",
                        "id": fc_id,
                        "call_id": tool_call_id,
                        "name": tool_name,
                        "arguments": args_str,
                        "status": "completed",
                    },
                    "sequence_number": self.seq,
                },
            )
            self.seq += 1
            self.output_index += 1
            self.current_item_type = None
            self.current_item_id = None

        elif event_type == "finish":
            if not self.has_any_output:
                raise AdapterError(message="Upstream model returned an empty response", status_code=502)

            if self.current_item_type is not None:
                yield from self.close_current_item()

            usage = parse_usage(event.get("totalUsage"))
            full_text = "".join(self.text_buf)
            output_items: list[dict] = []
            if self.reasoning_buf:
                rs_id = self.reasoning_item_id or generate_id("rs_")
                output_items.append(
                    {
                        "type": "reasoning",
                        "id": rs_id,
                        "content": [{"type": "reasoning_text", "text": "".join(self.reasoning_buf)}],
                        "status": "completed",
                    }
                )
            if full_text:
                msg_id = self.text_item_id or generate_id("msg_")
                output_items.append(
                    {
                        "type": "message",
                        "id": msg_id,
                        "role": "assistant",
                        "status": "completed",
                        "content": [{"type": "output_text", "text": full_text, "annotations": []}],
                    }
                )
            for i, fc_id in enumerate(self.fc_item_ids):
                output_items.append(
                    {
                        "type": "function_call",
                        "id": fc_id,
                        "call_id": self.fc_call_ids[i] if i < len(self.fc_call_ids) else generate_id("call_", 8),
                        "name": self.fc_names[i] if i < len(self.fc_names) else "",
                        "arguments": self.fc_args[i] if i < len(self.fc_args) else "{}",
                        "status": "completed",
                    }
                )

            yield _sse(
                "response.completed",
                {
                    "response": {
                        "id": self.response_id,
                        "object": "response",
                        "status": "completed",
                        "created_at": self.created,
                        "completed_at": time.time(),
                        "model": self.model,
                        "output": output_items,
                        "usage": usage,
                        "output_text": full_text,
                    },
                    "sequence_number": self.seq,
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
                    "sequence_number": self.seq,
                },
            )
            return

    def finalize(self):
        if not self.has_any_output:
            raise AdapterError(message="Upstream model returned an empty response", status_code=502)
        yield _sse(
            "error",
            {
                "message": "Upstream stream ended before finish",
                "sequence_number": self.seq,
            },
        )


async def translate_responses_stream(
    cc_stream: AsyncGenerator[dict, None],
    model: str,
) -> AsyncGenerator[str, None]:
    response_id = generate_id("resp_")
    created = time.time()
    state = _ResponsesStreamState(response_id, model, created)

    async for event in cc_stream:
        event_type = event.get("type")
        if event_type == "finish":
            for chunk in state.process_event(event):
                yield chunk
            return
        elif event_type == "error":
            for chunk in state.process_event(event):
                yield chunk
            return
        else:
            for chunk in state.process_event(event):
                yield chunk

    for chunk in state.finalize():
        yield chunk


async def collect_and_translate_responses_nonstream(
    cc_stream: AsyncGenerator[dict, None],
    model: str,
) -> dict:
    response_id = generate_id("resp_")
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
                "id": generate_id("fc_"),
                "call_id": event.get("toolCallId", generate_id("call_", 8)),
                "name": tool_name,
                "arguments": json.dumps(normalize_args(tool_name, raw_args), ensure_ascii=False),
                "status": "completed",
            }
            tool_calls.append(tc)

        elif event_type == "finish":
            usage = parse_usage(event.get("totalUsage"))

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
                "id": generate_id("rs_"),
                "content": [{"type": "reasoning_text", "text": "".join(reasoning_parts)}],
                "status": "completed",
            }
        )

    if text:
        output_items.append(
            {
                "type": "message",
                "id": generate_id("msg_"),
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
