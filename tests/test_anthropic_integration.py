from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from cc_adapter.core.runtime import init as admin_init
from cc_adapter.command_code.client import CommandCodeClient
from cc_adapter.core.config import AppConfig
from cc_adapter.main import app


def _make_mock_generate(mock_client, events: list[dict], events_second: list[dict] | None = None):
    call_count = 0

    async def _generate(body, extra_headers=None):
        nonlocal call_count
        call_count += 1
        chosen = events_second if call_count == 2 and events_second else events
        for event in chosen:
            yield event

    mock_client.generate = _generate


TRANSPORT = ASGITransport(app=app)


@pytest.fixture
def client():
    return AsyncClient(transport=TRANSPORT, base_url="http://test")


def _parse_sse(text: str) -> list[dict]:
    events = []
    for block in text.strip().split("\n\n"):
        if not block.strip():
            continue
        event_type = ""
        data = {}
        for line in block.strip().split("\n"):
            if line.startswith("event: "):
                event_type = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        events.append({"event": event_type, "data": data})
    return events


def _setup(
    cfg_overrides: dict | None = None, events: list[dict] | None = None, events_second: list[dict] | None = None
):
    cfg = AppConfig(**(cfg_overrides or {}), cc_api_key="test_key_123")
    mock_client = MagicMock(spec=CommandCodeClient)
    mock_client.api_key = "test_key_123"
    mock_client.base_url = "https://api.commandcode.ai"
    if events is not None:
        _make_mock_generate(mock_client, events, events_second)
    admin_init(cfg, mock_client)
    return cfg, mock_client


# ====== Non-streaming tool call tests ======


@pytest.mark.asyncio
async def test_nonstream_single_tool_call(client):
    cfg, mock_client = _setup(
        events=[
            {"type": "tool-call", "toolCallId": "call_abc", "toolName": "Read", "input": {"path": "/tmp/test.txt"}},
            {"type": "finish", "finishReason": "tool_calls", "totalUsage": {"inputTokens": 50, "outputTokens": 20}},
        ]
    )
    payload = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 8000,
        "messages": [{"role": "user", "content": "read file /tmp/test.txt"}],
        "tools": [
            {
                "name": "Read",
                "description": "Read a file",
                "input_schema": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            }
        ],
        "stream": False,
    }
    async with client as c:
        resp = await c.post("/v1/messages", json=payload)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    data = resp.json()
    assert data["type"] == "message"
    assert data["role"] == "assistant"
    assert data["stop_reason"] == "tool_use"

    content = data["content"]
    assert len(content) == 1
    assert content[0]["type"] == "tool_use"
    assert content[0]["name"] == "Read"
    assert content[0]["input"] == {"path": "/tmp/test.txt"}


@pytest.mark.asyncio
async def test_nonstream_text_and_tool_call(client):
    _setup(
        events=[
            {"type": "text-delta", "text": "Let me read that file"},
            {"type": "tool-call", "toolCallId": "call_abc", "toolName": "Read", "input": {"path": "/tmp/test.txt"}},
            {"type": "finish", "finishReason": "tool_calls", "totalUsage": {"inputTokens": 50, "outputTokens": 25}},
        ]
    )
    payload = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 8000,
        "messages": [{"role": "user", "content": "read file /tmp/test.txt"}],
        "tools": [
            {
                "name": "Read",
                "description": "Read a file",
                "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
            }
        ],
        "stream": False,
    }
    async with client as c:
        resp = await c.post("/v1/messages", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["content"]) == 2
    assert data["content"][0]["type"] == "text"
    assert data["content"][1]["type"] == "tool_use"
    assert data["stop_reason"] == "tool_use"


@pytest.mark.asyncio
async def test_nonstream_multiple_tool_calls(client):
    _setup(
        events=[
            {"type": "tool-call", "toolCallId": "call_1", "toolName": "Read", "input": {"path": "/tmp/a.txt"}},
            {"type": "tool-call", "toolCallId": "call_2", "toolName": "Read", "input": {"path": "/tmp/b.txt"}},
            {"type": "finish", "finishReason": "tool_calls", "totalUsage": {"inputTokens": 50, "outputTokens": 30}},
        ]
    )
    payload = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 8000,
        "messages": [{"role": "user", "content": "read two files"}],
        "tools": [
            {
                "name": "Read",
                "description": "Read a file",
                "input_schema": {
                    "type": "object",
                    "properties": {"filePath": {"type": "string"}},
                    "required": ["filePath"],
                },
            }
        ],
        "stream": False,
    }
    async with client as c:
        resp = await c.post("/v1/messages", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["content"]) == 2
    assert data["content"][0]["type"] == "tool_use"
    assert data["content"][1]["type"] == "tool_use"


@pytest.mark.asyncio
async def test_nonstream_thinking_then_tool_call(client):
    _setup(
        events=[
            {"type": "reasoning-delta", "text": "I need to read the file to check its contents"},
            {"type": "tool-call", "toolCallId": "call_1", "toolName": "Read", "input": {"path": "/tmp/test.txt"}},
            {"type": "finish", "finishReason": "tool_calls", "totalUsage": {"inputTokens": 50, "outputTokens": 30}},
        ]
    )
    payload = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 8000,
        "messages": [{"role": "user", "content": "read file /tmp/test.txt"}],
        "tools": [
            {
                "name": "Read",
                "description": "Read a file",
                "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
            }
        ],
        "stream": False,
    }
    async with client as c:
        resp = await c.post("/v1/messages", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["content"]) == 2
    assert data["content"][0]["type"] == "thinking"
    assert data["content"][1]["type"] == "tool_use"
    assert data["stop_reason"] == "tool_use"


@pytest.mark.asyncio
async def test_stream_tool_call_only(client):
    _setup(
        events=[
            {"type": "tool-call", "toolCallId": "call_1", "toolName": "Read", "input": {"path": "/tmp/test.txt"}},
            {"type": "finish", "finishReason": "tool_calls", "totalUsage": {"inputTokens": 50, "outputTokens": 20}},
        ]
    )
    payload = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 8000,
        "messages": [{"role": "user", "content": "read file"}],
        "tools": [
            {
                "name": "Read",
                "description": "Read a file",
                "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
            }
        ],
        "stream": True,
    }
    async with client as c:
        resp = await c.post("/v1/messages", json=payload)
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert events[0]["event"] == "message_start"
    assert events[1]["event"] == "content_block_start"
    assert events[1]["data"]["content_block"]["type"] == "tool_use"
    assert events[1]["data"]["content_block"]["name"] == "Read"
    assert events[1]["data"]["content_block"]["input"] == {}
    assert events[2]["event"] == "content_block_delta"
    assert events[2]["data"]["delta"] == {"type": "input_json_delta", "partial_json": '{"path":"/tmp/test.txt"}'}
    assert events[3]["event"] == "content_block_stop"
    assert events[4]["event"] == "message_delta"
    assert events[4]["data"]["delta"]["stop_reason"] == "tool_use"
    assert events[5]["event"] == "message_stop"


@pytest.mark.asyncio
async def test_stream_text_then_tool_call(client):
    _setup(
        events=[
            {"type": "text-delta", "text": "Let me "},
            {"type": "text-delta", "text": "read the file"},
            {
                "type": "tool-call",
                "toolCallId": "call_1",
                "toolName": "Write",
                "input": {"path": "/tmp/test.txt", "old_str": "foo", "new_str": "bar"},
            },
            {"type": "finish", "finishReason": "tool_calls", "totalUsage": {"inputTokens": 50, "outputTokens": 25}},
        ]
    )
    payload = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 8000,
        "messages": [{"role": "user", "content": "edit file"}],
        "tools": [
            {
                "name": "Write",
                "description": "Write a file",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "oldString": {"type": "string"},
                        "newString": {"type": "string"},
                    },
                    "required": ["path", "oldString", "newString"],
                },
            }
        ],
        "stream": True,
    }
    async with client as c:
        resp = await c.post("/v1/messages", json=payload)
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert events[0]["event"] == "message_start"
    assert events[1]["event"] == "content_block_start"
    assert events[1]["data"]["content_block"]["type"] == "text"
    assert events[4]["event"] == "content_block_stop"
    assert events[5]["event"] == "content_block_start"
    assert events[5]["data"]["content_block"]["type"] == "tool_use"
    assert events[5]["data"]["content_block"]["name"] == "Write"
    assert events[5]["data"]["content_block"]["input"] == {}
    assert events[6]["event"] == "content_block_delta"
    assert events[6]["data"]["delta"] == {
        "type": "input_json_delta",
        "partial_json": '{"path":"/tmp/test.txt","oldString":"foo","newString":"bar"}',
    }


@pytest.mark.asyncio
async def test_stream_thinking_then_tool_call(client):
    _setup(
        events=[
            {"type": "reasoning-delta", "text": "I need to read the file..."},
            {"type": "tool-call", "toolCallId": "call_1", "toolName": "Read", "input": {"path": "/tmp/test.txt"}},
            {"type": "finish", "finishReason": "tool_calls", "totalUsage": {"inputTokens": 50, "outputTokens": 20}},
        ]
    )
    payload = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 8000,
        "messages": [{"role": "user", "content": "read file"}],
        "tools": [
            {
                "name": "Read",
                "description": "Read a file",
                "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
            }
        ],
        "stream": True,
    }
    async with client as c:
        resp = await c.post("/v1/messages", json=payload)
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert events[0]["event"] == "message_start"
    assert events[1]["event"] == "content_block_start"
    assert events[1]["data"]["content_block"]["type"] == "thinking"
    assert events[3]["event"] == "content_block_stop"
    assert events[4]["event"] == "content_block_start"
    assert events[4]["data"]["content_block"]["type"] == "tool_use"


@pytest.mark.asyncio
async def test_stream_multiple_tool_calls(client):
    _setup(
        events=[
            {"type": "tool-call", "toolCallId": "call_1", "toolName": "Read", "input": {"path": "/tmp/a.txt"}},
            {"type": "tool-call", "toolCallId": "call_2", "toolName": "Read", "input": {"path": "/tmp/b.txt"}},
            {"type": "finish", "finishReason": "tool_calls", "totalUsage": {"inputTokens": 50, "outputTokens": 30}},
        ]
    )
    payload = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 8000,
        "messages": [{"role": "user", "content": "read two files"}],
        "tools": [
            {
                "name": "Read",
                "description": "Read a file",
                "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
            }
        ],
        "stream": True,
    }
    async with client as c:
        resp = await c.post("/v1/messages", json=payload)
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert len(events) == 9
    assert events[1]["data"]["content_block"]["type"] == "tool_use"
    assert events[2]["data"]["delta"] == {"type": "input_json_delta", "partial_json": '{"path":"/tmp/a.txt"}'}
    assert events[4]["data"]["content_block"]["type"] == "tool_use"
    assert events[5]["data"]["delta"] == {"type": "input_json_delta", "partial_json": '{"path":"/tmp/b.txt"}'}


@pytest.mark.asyncio
async def test_nonstream_multi_turn_tool_result(client):
    _setup(
        events=[
            {"type": "text-delta", "text": "The file contains: hello world"},
            {"type": "finish", "finishReason": "end_turn", "totalUsage": {"inputTokens": 100, "outputTokens": 10}},
        ]
    )
    payload = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 8000,
        "messages": [
            {"role": "user", "content": "read /tmp/test.txt"},
            {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "call_1", "name": "Read", "input": {"filePath": "/tmp/test.txt"}}
                ],
            },
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "call_1", "content": "hello world"}]},
        ],
        "tools": [
            {
                "name": "Read",
                "description": "Read a file",
                "input_schema": {
                    "type": "object",
                    "properties": {"filePath": {"type": "string"}},
                    "required": ["filePath"],
                },
            }
        ],
        "stream": False,
    }
    async with client as c:
        resp = await c.post("/v1/messages", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["content"][0]["type"] == "text"


@pytest.mark.asyncio
async def test_stream_error_event(client):
    _setup(
        events=[
            {"type": "error", "error": {"message": "Rate limit exceeded", "statusCode": 429}},
        ]
    )
    payload = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 8000,
        "messages": [{"role": "user", "content": "hi"}],
        "stream": True,
    }
    async with client as c:
        resp = await c.post("/v1/messages", json=payload)
    events = _parse_sse(resp.text)
    assert events[0]["event"] == "error"
    assert "Rate limit" in events[0]["data"]["error"]["message"]


@pytest.mark.asyncio
async def test_nonstream_tool_call_edit_operation(client):
    _setup(
        events=[
            {
                "type": "tool-call",
                "toolCallId": "call_1",
                "toolName": "Edit",
                "input": {"path": "/tmp/test.py", "old_str": "foo", "new_str": "bar"},
            },
            {"type": "finish", "finishReason": "tool_calls", "totalUsage": {"inputTokens": 50, "outputTokens": 15}},
        ]
    )
    payload = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 8000,
        "messages": [{"role": "user", "content": "edit file"}],
        "tools": [
            {
                "name": "Edit",
                "description": "Edit a file",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "oldString": {"type": "string"},
                        "newString": {"type": "string"},
                    },
                    "required": ["path", "oldString", "newString"],
                },
            }
        ],
        "stream": False,
    }
    async with client as c:
        resp = await c.post("/v1/messages", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    tool_use = data["content"][0]
    assert tool_use["type"] == "tool_use"
    assert tool_use["name"] == "Edit"
    # CC API returns path/old_str/new_str; Anthropic response maps old_str→oldString, new_str→newString but keeps path as-is
    assert tool_use["input"] == {"path": "/tmp/test.py", "oldString": "foo", "newString": "bar"}


@pytest.mark.asyncio
async def test_nonstream_default_max_tokens_is_reasonable(client):
    cfg, mock_client = _setup(
        events=[
            {"type": "text-delta", "text": "Hello"},
            {"type": "finish", "finishReason": "end_turn", "totalUsage": {"inputTokens": 10, "outputTokens": 5}},
        ]
    )
    payload = {
        "model": "claude-sonnet-4-6",
        "messages": [{"role": "user", "content": "hi"}],
        "stream": False,
    }
    async with client as c:
        resp = await c.post("/v1/messages", json=payload)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_nonstream_access_key_auth(client):
    _setup(
        cfg_overrides={"access_key": "secret456"},
        events=[
            {"type": "text-delta", "text": "Hello"},
            {"type": "finish", "finishReason": "end_turn", "totalUsage": {"inputTokens": 10, "outputTokens": 5}},
        ],
    )
    payload = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 100,
        "messages": [{"role": "user", "content": "hi"}],
        "stream": False,
    }
    async with client as c:
        resp = await c.post("/v1/messages", json=payload, headers={"x-api-key": "secret456"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["content"][0]["text"] == "Hello"


# ====== Empty stream retry tests ======


@pytest.mark.asyncio
async def test_stream_empty_then_retry_succeeds(client):
    _setup(
        events=[
            {"type": "finish", "finishReason": "end_turn", "totalUsage": {"inputTokens": 0, "outputTokens": 0}},
        ],
        events_second=[
            {"type": "text-delta", "text": "Hello"},
            {"type": "finish", "finishReason": "end_turn", "totalUsage": {"inputTokens": 10, "outputTokens": 5}},
        ],
    )
    payload = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 8000,
        "messages": [{"role": "user", "content": "hi"}],
        "stream": True,
    }
    async with client as c:
        resp = await c.post("/v1/messages", json=payload)
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert events[0]["event"] == "message_start"
    assert any(e["event"] == "content_block_delta" and e["data"]["delta"].get("text") == "Hello" for e in events)


@pytest.mark.asyncio
async def test_stream_empty_both_attempts_returns_error(client):
    _setup(
        events=[
            {"type": "finish", "finishReason": "end_turn", "totalUsage": {"inputTokens": 0, "outputTokens": 0}},
        ],
        events_second=[
            {"type": "finish", "finishReason": "end_turn", "totalUsage": {"inputTokens": 0, "outputTokens": 0}},
        ],
    )
    payload = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 8000,
        "messages": [{"role": "user", "content": "hi"}],
        "stream": True,
    }
    async with client as c:
        resp = await c.post("/v1/messages", json=payload)
    events = _parse_sse(resp.text)
    assert any(e["event"] == "error" for e in events)


# ====== Empty text-delta edge case ======


@pytest.mark.asyncio
async def test_stream_empty_text_delta_skipped_retry_succeeds(client):
    """text-delta with empty text must not emit chunks, so retry works."""
    _setup(
        events=[
            {"type": "text-delta", "text": ""},
            {"type": "finish", "finishReason": "end_turn", "totalUsage": {"inputTokens": 0, "outputTokens": 0}},
        ],
        events_second=[
            {"type": "text-delta", "text": "Hello"},
            {"type": "finish", "finishReason": "end_turn", "totalUsage": {"inputTokens": 10, "outputTokens": 5}},
        ],
    )
    payload = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 8000,
        "messages": [{"role": "user", "content": "hi"}],
        "stream": True,
    }
    async with client as c:
        resp = await c.post("/v1/messages", json=payload)
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert events[0]["event"] == "message_start"
    assert any(e["event"] == "content_block_delta" and e["data"]["delta"].get("text") == "Hello" for e in events)


@pytest.mark.asyncio
async def test_stream_error_not_retried(client):
    """Non-empty AdapterError (e.g. rate limit) must NOT be retried."""
    _setup(
        events=[
            {"type": "error", "error": {"message": "Rate limit exceeded", "statusCode": 429}},
        ],
        events_second=[
            {"type": "text-delta", "text": "Should not appear"},
            {"type": "finish", "finishReason": "end_turn", "totalUsage": {"inputTokens": 10, "outputTokens": 5}},
        ],
    )
    payload = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 8000,
        "messages": [{"role": "user", "content": "hi"}],
        "stream": True,
    }
    async with client as c:
        resp = await c.post("/v1/messages", json=payload)
    events = _parse_sse(resp.text)
    assert len(events) == 1
    assert events[0]["event"] == "error"
    assert "Rate limit" in events[0]["data"]["error"]["message"]


# ====== Truncated stream tests ======


@pytest.mark.asyncio
async def test_stream_truncated_mid_text(client):
    _setup(
        events=[
            {"type": "text-delta", "text": "Hello"},
        ]
    )
    payload = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 8000,
        "messages": [{"role": "user", "content": "hi"}],
        "stream": True,
    }
    async with client as c:
        resp = await c.post("/v1/messages", json=payload)
    events = _parse_sse(resp.text)
    # Should get message_start, content_block_start, delta, content_block_stop, then error
    assert events[0]["event"] == "message_start"
    assert any(e["event"] == "content_block_delta" for e in events)
    assert any(e["event"] == "content_block_stop" for e in events)
    assert any(e["event"] == "error" for e in events)
