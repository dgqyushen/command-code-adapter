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
        for line in block.strip().split("\n"):
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
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


# ====== Non-streaming tests ======


@pytest.mark.asyncio
async def test_nonstream_text_only(client):
    _setup(
        events=[
            {"type": "text-delta", "text": "Hello world"},
            {"type": "finish", "finishReason": "end_turn", "totalUsage": {"inputTokens": 10, "outputTokens": 5}},
        ]
    )
    payload = {"model": "deepseek-v4-flash", "input": "Say hello", "stream": False}
    async with client as c:
        resp = await c.post("/v1/responses", json=payload)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data["object"] == "response"
    assert data["status"] == "completed"
    assert len(data["output"]) == 1
    assert data["output"][0]["type"] == "message"
    assert data["output"][0]["content"][0]["text"] == "Hello world"
    assert data["output_text"] == "Hello world"


@pytest.mark.asyncio
async def test_nonstream_text_with_reasoning(client):
    _setup(
        events=[
            {"type": "reasoning-delta", "text": "Let me think..."},
            {"type": "text-delta", "text": "The answer is 42"},
            {"type": "finish", "finishReason": "end_turn", "totalUsage": {"inputTokens": 20, "outputTokens": 15}},
        ]
    )
    payload = {"model": "deepseek-v4-flash", "input": "What is 6*7?", "stream": False}
    async with client as c:
        resp = await c.post("/v1/responses", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["output"]) == 2
    assert data["output"][0]["type"] == "reasoning"
    assert data["output"][1]["type"] == "message"
    assert data["output_text"] == "The answer is 42"


@pytest.mark.asyncio
async def test_nonstream_tool_call(client):
    _setup(
        events=[
            {"type": "tool-call", "toolCallId": "call_abc", "toolName": "Read", "input": {"path": "/tmp/test.txt"}},
            {"type": "finish", "finishReason": "tool_calls", "totalUsage": {"inputTokens": 50, "outputTokens": 20}},
        ]
    )
    payload = {
        "model": "deepseek-v4-flash",
        "input": "Read /tmp/test.txt",
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
        resp = await c.post("/v1/responses", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["output"]) == 1
    assert data["output"][0]["type"] == "function_call"
    assert data["output"][0]["name"] == "Read"
    assert data["output"][0]["call_id"] == "call_abc"


@pytest.mark.asyncio
async def test_nonstream_text_and_tool_call(client):
    _setup(
        events=[
            {"type": "text-delta", "text": "Let me read that file"},
            {"type": "tool-call", "toolCallId": "call_1", "toolName": "Read", "input": {"path": "/tmp/test.txt"}},
            {"type": "finish", "finishReason": "tool_calls", "totalUsage": {"inputTokens": 50, "outputTokens": 25}},
        ]
    )
    payload = {
        "model": "deepseek-v4-flash",
        "input": "read file",
        "tools": [
            {
                "name": "Read",
                "description": "Read",
                "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
            }
        ],
        "stream": False,
    }
    async with client as c:
        resp = await c.post("/v1/responses", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["output"]) == 2
    assert data["output"][0]["type"] == "message"
    assert data["output"][1]["type"] == "function_call"


# ====== Streaming tests ======


@pytest.mark.asyncio
async def test_stream_text_only(client):
    _setup(
        events=[
            {"type": "text-delta", "text": "Hello"},
            {"type": "text-delta", "text": " world"},
            {"type": "finish", "finishReason": "end_turn", "totalUsage": {"inputTokens": 10, "outputTokens": 5}},
        ]
    )
    payload = {"model": "deepseek-v4-flash", "input": "Say hi", "stream": True}
    async with client as c:
        resp = await c.post("/v1/responses", json=payload)
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    types = [e["type"] for e in events]
    assert "response.created" in types
    assert "response.in_progress" in types
    assert "response.output_item.added" in types
    assert "response.content_part.added" in types
    assert "response.output_text.delta" in types
    assert "response.content_part.done" in types
    assert "response.output_text.done" in types
    assert "response.output_item.done" in types
    assert "response.completed" in types


@pytest.mark.asyncio
async def test_stream_empty_upstream_raises_error(client):
    empty_events: list[dict] = []
    call_count = 0

    async def _empty_generate(body, extra_headers=None):
        nonlocal call_count
        call_count += 1
        for event in empty_events:
            yield event

    cfg = AppConfig(cc_api_key="test_key_123")
    mock_client = MagicMock(spec=CommandCodeClient)
    mock_client.api_key = "test_key_123"
    mock_client.base_url = "https://api.commandcode.ai"
    mock_client.generate = _empty_generate
    admin_init(cfg, mock_client)

    payload = {"model": "deepseek-v4-flash", "input": "hi", "stream": True}
    async with client as c:
        resp = await c.post("/v1/responses", json=payload)
    assert resp.status_code in (200, 401, 502)
    if resp.status_code == 200:
        events = _parse_sse(resp.text)
        assert len(events) == 1
        assert events[0]["type"] == "error"


@pytest.mark.asyncio
async def test_stream_reasoning_then_text(client):
    _setup(
        events=[
            {"type": "reasoning-delta", "text": "Thinking..."},
            {"type": "text-delta", "text": "Answer: 42"},
            {"type": "finish", "finishReason": "end_turn", "totalUsage": {"inputTokens": 10, "outputTokens": 8}},
        ]
    )
    payload = {"model": "deepseek-v4-flash", "input": "What is 6*7?", "stream": True}
    async with client as c:
        resp = await c.post("/v1/responses", json=payload)
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    types = [e["type"] for e in events]
    assert "response.reasoning_text.delta" in types
    assert "response.output_text.delta" in types
    reasoning_deltas = [e for e in events if e["type"] == "response.reasoning_text.delta"]
    assert reasoning_deltas[0]["delta"] == "Thinking..."


@pytest.mark.asyncio
async def test_stream_tool_call(client):
    _setup(
        events=[
            {"type": "tool-call", "toolCallId": "call_1", "toolName": "Read", "input": {"filePath": "/tmp/test.txt"}},
            {"type": "finish", "finishReason": "tool_calls", "totalUsage": {"inputTokens": 50, "outputTokens": 20}},
        ]
    )
    payload = {
        "model": "deepseek-v4-flash",
        "input": "read file",
        "tools": [
            {
                "name": "Read",
                "description": "Read",
                "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
            }
        ],
        "stream": True,
    }
    async with client as c:
        resp = await c.post("/v1/responses", json=payload)
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    types = [e["type"] for e in events]
    assert "response.output_item.added" in types
    assert "response.function_call_arguments.delta" in types
    assert "response.function_call_arguments.done" in types
    assert "response.output_item.done" in types
    assert "response.completed" in types
    fc_args_done = [e for e in events if e["type"] == "response.function_call_arguments.done"]
    args = json.loads(fc_args_done[0]["arguments"])
    assert args.get("filePath") == "/tmp/test.txt"
    completed = [e for e in events if e["type"] == "response.completed"]
    assert len(completed) == 1
    output = completed[0]["response"]["output"]
    assert len(output) == 1
    assert output[0]["type"] == "function_call"
    assert output[0]["arguments"] != "{}"
    completed_args = json.loads(output[0]["arguments"])
    assert completed_args.get("filePath") == "/tmp/test.txt"


@pytest.mark.asyncio
async def test_stream_error_event(client):
    _setup(
        events=[
            {"type": "error", "error": {"message": "Rate limit exceeded", "statusCode": 429}},
        ]
    )
    payload = {"model": "deepseek-v4-flash", "input": "hi", "stream": True}
    async with client as c:
        resp = await c.post("/v1/responses", json=payload)
    events = _parse_sse(resp.text)
    error_events = [e for e in events if e["type"] == "error"]
    assert len(error_events) > 0
    assert "Rate limit" in error_events[0]["message"]


@pytest.mark.asyncio
async def test_empty_then_retry_succeeds(client):
    _setup(
        events=[
            {"type": "finish", "finishReason": "end_turn", "totalUsage": {"inputTokens": 0, "outputTokens": 0}},
        ],
        events_second=[
            {"type": "text-delta", "text": "Hello after retry"},
            {"type": "finish", "finishReason": "end_turn", "totalUsage": {"inputTokens": 10, "outputTokens": 5}},
        ],
    )
    payload = {"model": "deepseek-v4-flash", "input": "hi", "stream": True}
    async with client as c:
        resp = await c.post("/v1/responses", json=payload)
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert any(e["type"] == "response.output_text.delta" and e["delta"] == "Hello after retry" for e in events)


@pytest.mark.asyncio
async def test_nonstream_access_key_auth(client):
    _setup(
        cfg_overrides={"access_key": "secret123"},
        events=[
            {"type": "text-delta", "text": "Hello"},
            {"type": "finish", "finishReason": "end_turn", "totalUsage": {"inputTokens": 10, "outputTokens": 5}},
        ],
    )
    payload = {"model": "deepseek-v4-flash", "input": "hi", "stream": False}
    async with client as c:
        resp = await c.post("/v1/responses", json=payload, headers={"Authorization": "Bearer secret123"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["output_text"] == "Hello"


@pytest.mark.asyncio
async def test_unauthorized_without_key(client):
    _setup(cfg_overrides={"access_key": "secret123"})
    payload = {"model": "deepseek-v4-flash", "input": "hi", "stream": False}
    async with client as c:
        resp = await c.post("/v1/responses", json=payload)
    assert resp.status_code == 401
