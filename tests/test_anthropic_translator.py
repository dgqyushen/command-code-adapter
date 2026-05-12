import json
import logging

import pytest

from cc_adapter.anthropic.models import AnthropicMessage, AnthropicRequest
from cc_adapter.anthropic.request import AnthropicTranslator
from cc_adapter.anthropic.response import collect_and_translate_anthropic_nonstream, translate_anthropic_stream


@pytest.fixture
def translator():
    return AnthropicTranslator()


def test_basic_text_message(translator):
    req = AnthropicRequest(
        model="claude-sonnet-4-6",
        messages=[AnthropicMessage(role="user", content="hello")],
    )
    body, headers = translator.translate(req)
    assert body["params"]["model"] == "claude-sonnet-4-6"
    assert body["params"]["messages"][0]["content"] == [{"type": "text", "text": "hello"}]
    assert "Authorization" not in headers


def test_system_prompt_string(translator):
    req = AnthropicRequest(
        model="claude-sonnet-4-6",
        messages=[AnthropicMessage(role="user", content="hi")],
        system="You are helpful.",
    )
    body, _ = translator.translate(req)
    assert body["params"]["system"] == "You are helpful."


def test_system_prompt_list(translator):
    req = AnthropicRequest(
        model="claude-sonnet-4-6",
        messages=[AnthropicMessage(role="user", content="hi")],
        system=[{"type": "text", "text": "You are helpful."}],
    )
    body, _ = translator.translate(req)
    assert body["params"]["system"] == "You are helpful."


def test_tool_definition(translator):
    req = AnthropicRequest(
        model="claude-sonnet-4-6",
        messages=[AnthropicMessage(role="user", content="read a file")],
        tools=[
            {
                "name": "read",
                "description": "Read a file",
                "input_schema": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            }
        ],
    )
    body, _ = translator.translate(req)
    assert len(body["params"]["tools"]) == 1
    assert body["params"]["tools"][0]["name"] == "read"
    assert body["params"]["tools"][0]["input_schema"]["properties"]["path"]["type"] == "string"


def test_tool_choice_auto(translator):
    req = AnthropicRequest(
        model="claude-sonnet-4-6",
        messages=[AnthropicMessage(role="user", content="hi")],
        tool_choice={"type": "auto"},
    )
    body, _ = translator.translate(req)
    assert body["params"]["tool_choice"] == {"type": "auto"}


def test_tool_choice_tool(translator):
    req = AnthropicRequest(
        model="claude-sonnet-4-6",
        messages=[AnthropicMessage(role="user", content="hi")],
        tool_choice={"type": "tool", "name": "read"},
    )
    body, _ = translator.translate(req)
    assert body["params"]["tool_choice"] == {"type": "tool", "name": "read"}


def test_thinking_maps_to_reasoning_effort_low(translator):
    req = AnthropicRequest(
        model="claude-sonnet-4-6",
        messages=[AnthropicMessage(role="user", content="hello")],
        thinking={"type": "enabled", "budget_tokens": 2000},
    )
    body, _ = translator.translate(req)
    assert body["params"]["reasoning_effort"] == "low"


def test_thinking_maps_to_reasoning_effort_high(translator):
    req = AnthropicRequest(
        model="claude-sonnet-4-6",
        messages=[AnthropicMessage(role="user", content="hello")],
        thinking={"type": "enabled", "budget_tokens": 12000},
    )
    body, _ = translator.translate(req)
    assert body["params"]["reasoning_effort"] == "high"


def test_thinking_maps_to_reasoning_effort_xhigh(translator):
    req = AnthropicRequest(
        model="claude-sonnet-4-6",
        messages=[AnthropicMessage(role="user", content="hello")],
        thinking={"type": "enabled", "budget_tokens": 20000},
    )
    body, _ = translator.translate(req)
    assert body["params"]["reasoning_effort"] == "xhigh"


def test_no_thinking_omits_reasoning_effort(translator):
    req = AnthropicRequest(
        model="claude-sonnet-4-6",
        messages=[AnthropicMessage(role="user", content="hello")],
    )
    body, _ = translator.translate(req)
    assert "reasoning_effort" not in body["params"]


def test_tool_use_content_block(translator):
    req = AnthropicRequest(
        model="claude-sonnet-4-6",
        messages=[
            AnthropicMessage(role="user", content="read file"),
            AnthropicMessage(
                role="assistant",
                content=[
                    {
                        "type": "tool_use",
                        "id": "call_1",
                        "name": "read",
                        "input": {"filePath": "/tmp/test"},
                    }
                ],
            ),
        ],
    )
    body, _ = translator.translate(req)
    msg = body["params"]["messages"][1]
    assert msg["content"] == [
        {
            "type": "tool-call",
            "toolCallId": "call_1",
            "toolName": "read",
            "input": {"path": "/tmp/test"},
        }
    ]


def test_multi_turn_tool_use_tool_result(translator):
    req = AnthropicRequest(
        model="claude-sonnet-4-6",
        messages=[
            AnthropicMessage(role="user", content="read file"),
            AnthropicMessage(
                role="assistant",
                content=[
                    {
                        "type": "tool_use",
                        "id": "call_1",
                        "name": "read",
                        "input": {"filePath": "/tmp/test"},
                    }
                ],
            ),
            AnthropicMessage(
                role="user",
                content=[
                    {
                        "type": "tool_result",
                        "tool_use_id": "call_1",
                        "content": "file contents",
                    }
                ],
            ),
        ],
    )
    body, _ = translator.translate(req)
    msgs = body["params"]["messages"]
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["content"] == [
        {"type": "tool-call", "toolCallId": "call_1", "toolName": "read", "input": {"path": "/tmp/test"}}
    ]
    assert msgs[2]["role"] == "tool"
    assert msgs[2]["content"] == [
        {
            "type": "tool-result",
            "toolCallId": "call_1",
            "toolName": "read",
            "output": {"type": "text", "value": "file contents"},
        }
    ]


def test_multi_turn_mixed_text_and_tool_result(translator):
    req = AnthropicRequest(
        model="claude-sonnet-4-6",
        messages=[
            AnthropicMessage(role="user", content="read file"),
            AnthropicMessage(
                role="assistant",
                content=[
                    {
                        "type": "tool_use",
                        "id": "call_1",
                        "name": "read",
                        "input": {"filePath": "/tmp/test"},
                    }
                ],
            ),
            AnthropicMessage(
                role="user",
                content=[
                    {"type": "text", "text": "Now write the result"},
                    {
                        "type": "tool_result",
                        "tool_use_id": "call_1",
                        "content": "file contents",
                    },
                ],
            ),
        ],
    )
    body, _ = translator.translate(req)
    msgs = body["params"]["messages"]
    assert msgs[2]["role"] == "user"
    assert msgs[2]["content"] == [{"type": "text", "text": "Now write the result"}]
    assert msgs[3]["role"] == "tool"
    assert msgs[3]["content"] == [
        {
            "type": "tool-result",
            "toolCallId": "call_1",
            "toolName": "read",
            "output": {"type": "text", "value": "file contents"},
        }
    ]


def test_tool_result_content_block(translator):
    req = AnthropicRequest(
        model="claude-sonnet-4-6",
        messages=[
            AnthropicMessage(
                role="user",
                content=[
                    {
                        "type": "tool_result",
                        "tool_use_id": "call_1",
                        "content": "file contents",
                    }
                ],
            ),
        ],
    )
    body, _ = translator.translate(req)
    assert len(body["params"]["messages"]) == 1
    assert body["params"]["messages"][0]["role"] == "tool"
    assert body["params"]["messages"][0]["content"] == [
        {
            "type": "tool-result",
            "toolCallId": "call_1",
            "toolName": "unknown",
            "output": {"type": "text", "value": "file contents"},
        }
    ]


def test_unsupported_params_logged_as_warning(translator, caplog):
    caplog.set_level(logging.WARNING)
    req = AnthropicRequest(
        model="claude-sonnet-4-6",
        messages=[AnthropicMessage(role="user", content="hi")],
        top_p=0.9,
        top_k=5,
        stop_sequences=["\n"],
    )
    translator.translate(req)
    assert any("top_p" in r.message for r in caplog.records)
    assert any("top_k" in r.message for r in caplog.records)
    assert any("stop_sequences" in r.message for r in caplog.records)


def test_image_content_block_skipped(translator, caplog):
    caplog.set_level(logging.WARNING)
    req = AnthropicRequest(
        model="claude-sonnet-4-6",
        messages=[
            AnthropicMessage(
                role="user",
                content=[
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": "abc",
                        },
                    },
                    {"type": "text", "text": "what is this?"},
                ],
            ),
        ],
    )
    body, _ = translator.translate(req)
    assert "Image" in caplog.text
    assert body["params"]["messages"][0]["content"] == [{"type": "text", "text": "what is this?"}]


@pytest.mark.asyncio
async def test_nonstream_text_only():
    async def fake_stream():
        yield {"type": "text-delta", "text": "Hello"}
        yield {"type": "text-delta", "text": " World"}
        yield {"type": "finish", "finishReason": "end_turn", "totalUsage": {"inputTokens": 10, "outputTokens": 5}}

    resp = await collect_and_translate_anthropic_nonstream(fake_stream(), "claude-sonnet-4-6")
    assert resp.type == "message"
    assert resp.role == "assistant"
    assert len(resp.content) == 1
    assert resp.content[0]["type"] == "text"
    assert resp.content[0]["text"] == "Hello World"
    assert resp.stop_reason == "end_turn"
    assert resp.usage.input_tokens == 10
    assert resp.usage.output_tokens == 5


@pytest.mark.asyncio
async def test_nonstream_with_thinking():
    async def fake_stream():
        yield {"type": "reasoning-delta", "text": "I need to think..."}
        yield {"type": "text-delta", "text": "Answer: 42"}
        yield {"type": "finish", "finishReason": "end_turn", "totalUsage": {"inputTokens": 10, "outputTokens": 8}}

    resp = await collect_and_translate_anthropic_nonstream(fake_stream(), "claude-sonnet-4-6")
    assert len(resp.content) == 2
    assert resp.content[0]["type"] == "thinking"
    assert resp.content[0]["thinking"] == "I need to think..."
    assert resp.content[1]["type"] == "text"
    assert resp.content[1]["text"] == "Answer: 42"


@pytest.mark.asyncio
async def test_nonstream_with_tool_calls():
    async def fake_stream():
        yield {"type": "text-delta", "text": "Let me read the file"}
        yield {"type": "tool-call", "toolCallId": "call_1", "toolName": "read", "input": {"path": "/tmp/test"}}
        yield {"type": "finish", "finishReason": "tool_calls", "totalUsage": {"inputTokens": 10, "outputTokens": 15}}

    resp = await collect_and_translate_anthropic_nonstream(fake_stream(), "claude-sonnet-4-6")
    assert len(resp.content) == 2
    assert resp.content[0]["type"] == "text"
    assert resp.content[0]["text"] == "Let me read the file"
    assert resp.content[1]["type"] == "tool_use"
    assert resp.content[1]["name"] == "read"
    assert resp.stop_reason == "tool_use"


@pytest.mark.asyncio
async def test_nonstream_thinking_only_fallback_to_text():
    async def fake_stream():
        yield {"type": "reasoning-delta", "text": "thinking hard"}
        yield {"type": "finish", "finishReason": "end_turn", "totalUsage": {"inputTokens": 10, "outputTokens": 5}}

    resp = await collect_and_translate_anthropic_nonstream(fake_stream(), "claude-sonnet-4-6")
    assert len(resp.content) == 1
    assert resp.content[0]["type"] == "text"
    assert resp.content[0]["text"] == "thinking hard"


@pytest.mark.asyncio
async def test_nonstream_empty_response_raises_error():
    async def fake_stream():
        yield {"type": "finish", "finishReason": "end_turn", "totalUsage": {"inputTokens": 10, "outputTokens": 0}}

    with pytest.raises(Exception):
        await collect_and_translate_anthropic_nonstream(fake_stream(), "claude-sonnet-4-6")


@pytest.mark.asyncio
async def test_nonstream_error_event_raises():
    async def fake_stream():
        yield {"type": "error", "error": {"message": "CC error", "statusCode": 502}}

    with pytest.raises(Exception, match="CC error"):
        await collect_and_translate_anthropic_nonstream(fake_stream(), "claude-sonnet-4-6")


def _parse_sse_events(sse_text: str) -> list[tuple[str, dict]]:
    events = []
    for block in sse_text.strip().split("\n\n"):
        if not block.strip():
            continue
        lines = block.strip().split("\n")
        event_type = ""
        data = {}
        for line in lines:
            if line.startswith("event: "):
                event_type = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        if event_type:
            events.append((event_type, data))
    return events


@pytest.mark.asyncio
async def test_stream_text_only():
    async def fake_stream():
        yield {"type": "text-delta", "text": "Hello"}
        yield {"type": "text-delta", "text": " World"}
        yield {"type": "finish", "finishReason": "end_turn", "totalUsage": {"inputTokens": 10, "outputTokens": 5}}

    chunks = [c async for c in translate_anthropic_stream(fake_stream(), "claude-sonnet-4-6")]
    events = _parse_sse_events("".join(chunks))

    assert events[0][0] == "message_start"
    assert events[0][1]["message"]["model"] == "claude-sonnet-4-6"
    assert events[0][1]["message"]["role"] == "assistant"

    assert events[1][0] == "content_block_start"
    assert events[1][1]["content_block"]["type"] == "text"

    assert events[2][0] == "content_block_delta"
    assert events[2][1]["delta"]["type"] == "text_delta"
    assert events[2][1]["delta"]["text"] == "Hello"

    assert events[3][0] == "content_block_delta"
    assert events[3][1]["delta"]["text"] == " World"

    assert events[4][0] == "content_block_stop"

    assert events[5][0] == "message_delta"
    assert events[5][1]["delta"]["stop_reason"] == "end_turn"

    assert events[6][0] == "message_stop"

    assert len(events) == 7


@pytest.mark.asyncio
async def test_stream_with_thinking():
    async def fake_stream():
        yield {"type": "reasoning-delta", "text": "thinking..."}
        yield {"type": "text-delta", "text": "Answer: 42"}
        yield {"type": "finish", "finishReason": "end_turn", "totalUsage": {"inputTokens": 10, "outputTokens": 8}}

    chunks = [c async for c in translate_anthropic_stream(fake_stream(), "claude-sonnet-4-6")]
    events = _parse_sse_events("".join(chunks))

    assert events[0][0] == "message_start"
    assert events[1][0] == "content_block_start"
    assert events[1][1]["content_block"]["type"] == "thinking"
    assert events[2][0] == "content_block_delta"
    assert events[2][1]["delta"]["type"] == "thinking_delta"
    assert events[3][0] == "content_block_stop"
    assert events[4][0] == "content_block_start"
    assert events[4][1]["content_block"]["type"] == "text"
    assert events[5][0] == "content_block_delta"
    assert events[5][1]["delta"]["text"] == "Answer: 42"
    assert events[6][0] == "content_block_stop"
    assert events[7][0] == "message_delta"
    assert events[8][0] == "message_stop"


@pytest.mark.asyncio
async def test_stream_with_tool_call():
    async def fake_stream():
        yield {"type": "tool-call", "toolCallId": "call_1", "toolName": "read", "input": {"path": "/tmp/test"}}
        yield {"type": "finish", "finishReason": "tool_calls", "totalUsage": {"inputTokens": 10, "outputTokens": 5}}

    chunks = [c async for c in translate_anthropic_stream(fake_stream(), "claude-sonnet-4-6")]
    events = _parse_sse_events("".join(chunks))

    assert events[0][0] == "message_start"
    assert events[1][0] == "content_block_start"
    assert events[1][1]["content_block"]["type"] == "tool_use"
    assert events[1][1]["content_block"]["name"] == "read"
    assert events[1][1]["content_block"]["input"] == {}
    assert events[2][0] == "content_block_delta"
    assert events[2][1]["delta"] == {"type": "input_json_delta", "partial_json": '{"path":"/tmp/test"}'}
    assert events[3][0] == "content_block_stop"
    assert events[4][0] == "message_delta"
    assert events[4][1]["delta"]["stop_reason"] == "tool_use"
    assert events[5][0] == "message_stop"
