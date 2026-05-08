import json
import time

import pytest
from cc_adapter.errors import AdapterError
from cc_adapter.main import _stream_with_retry
from cc_adapter.translator.response import collect_and_translate_nonstream, translate_stream


@pytest.mark.asyncio
async def test_nonstream_simple_text():
    async def fake_stream():
        yield {"type": "text-delta", "text": "Hello"}
        yield {"type": "text-delta", "text": " world"}
        yield {"type": "finish", "finishReason": "end_turn", "totalUsage": {"inputTokens": 10, "outputTokens": 5}}

    result = await collect_and_translate_nonstream(fake_stream(), "claude-sonnet-4-6", time.time())
    assert result.choices[0].message.content == "Hello world"
    assert result.choices[0].finish_reason == "stop"
    assert result.usage.prompt_tokens == 10
    assert result.usage.completion_tokens == 5


@pytest.mark.asyncio
async def test_nonstream_tool_calls():
    async def fake_stream():
        yield {"type": "tool-call", "toolCallId": "call_1", "toolName": "read", "input": {"path": "/tmp/x"}}
        yield {"type": "finish", "finishReason": "tool_calls", "totalUsage": {"inputTokens": 5, "outputTokens": 2}}

    result = await collect_and_translate_nonstream(fake_stream(), "gpt-5.4", time.time())
    assert len(result.choices[0].message.tool_calls) == 1
    assert result.choices[0].message.tool_calls[0].function.name == "read"
    assert result.choices[0].message.tool_calls[0].function.arguments == '{"filePath": "/tmp/x"}'
    assert result.choices[0].finish_reason == "tool_calls"


@pytest.mark.asyncio
async def test_stream_output():
    async def fake_stream():
        yield {"type": "text-delta", "text": "Hi"}
        yield {"type": "finish", "finishReason": "end_turn", "totalUsage": {"inputTokens": 1, "outputTokens": 1}}

    chunks = []
    async for chunk in translate_stream(fake_stream(), "claude-sonnet-4-6", time.time()):
        chunks.append(chunk)

    assert len(chunks) == 3  # text-delta + finish + [DONE]
    assert 'data: {"id":"chatcmpl-' in chunks[0]
    assert '"content":"Hi"' in chunks[0]
    assert chunks[2] == "data: [DONE]\n\n"


@pytest.mark.asyncio
async def test_stream_tool_call_delta_includes_index():
    async def fake_stream():
        yield {"type": "tool-call", "toolCallId": "call_1", "toolName": "read", "input": {"path": "/tmp/x"}}
        yield {"type": "finish", "finishReason": "end_turn", "totalUsage": {"inputTokens": 5, "outputTokens": 2}}

    chunks = []
    async for chunk in translate_stream(fake_stream(), "deepseek-v4", time.time()):
        chunks.append(chunk)

    assert '"tool_calls":[{"index":0,"id":"call_1"' in chunks[0]


@pytest.mark.asyncio
async def test_stream_tool_call_finish_reason_overrides_end_turn():
    async def fake_stream():
        yield {"type": "tool-call", "toolCallId": "call_1", "toolName": "read", "input": {"path": "/tmp/x"}}
        yield {"type": "finish", "finishReason": "end_turn", "totalUsage": {"inputTokens": 5, "outputTokens": 2}}

    chunks = []
    async for chunk in translate_stream(fake_stream(), "deepseek-v4", time.time()):
        chunks.append(chunk)

    assert '"finish_reason":"tool_calls"' in chunks[1]


@pytest.mark.asyncio
async def test_stream_reasoning_content():
    async def fake_stream():
        yield {"type": "reasoning-delta", "text": "Let me think"}
        yield {"type": "reasoning-delta", "text": " about this step by step"}
        yield {"type": "text-delta", "text": "Here is my answer"}
        yield {"type": "finish", "finishReason": "end_turn", "totalUsage": {"inputTokens": 5, "outputTokens": 3}}

    chunks = []
    async for chunk in translate_stream(fake_stream(), "deepseek-v4", time.time()):
        chunks.append(chunk)

    # reasoning-delta chunks should have reasoning_content but no content
    assert '"reasoning_content":"Let me think"' in chunks[0]
    assert '"reasoning_content":" about this step by step"' in chunks[1]
    # text-delta chunk should have content but no reasoning_content
    assert '"content":"Here is my answer"' in chunks[2]
    assert chunks[-1] == "data: [DONE]\n\n"


@pytest.mark.asyncio
async def test_nonstream_reasoning_content():
    async def fake_stream():
        yield {"type": "reasoning-delta", "text": "First, I need to"}
        yield {"type": "reasoning-delta", "text": " break this down"}
        yield {"type": "text-delta", "text": "Answer: 42"}
        yield {"type": "finish", "finishReason": "end_turn", "totalUsage": {"inputTokens": 5, "outputTokens": 2}}

    result = await collect_and_translate_nonstream(fake_stream(), "deepseek-v4", time.time())
    assert result.choices[0].message.reasoning_content == "First, I need to break this down"
    assert result.choices[0].message.content == "Answer: 42"


@pytest.mark.asyncio
async def test_stream_reasoning_off_filters_reasoning():
    async def fake_stream():
        yield {"type": "reasoning-delta", "text": "Let me think"}
        yield {"type": "text-delta", "text": "Answer"}
        yield {"type": "finish", "finishReason": "end_turn", "totalUsage": {"inputTokens": 5, "outputTokens": 3}}

    chunks = []
    async for chunk in translate_stream(fake_stream(), "deepseek-v4", time.time(), reasoning_effort="off"):
        chunks.append(chunk)

    assert len(chunks) == 3  # text-delta + finish + [DONE]
    assert '"content":"Answer"' in chunks[0]
    assert "reasoning_content" not in chunks[0]


@pytest.mark.asyncio
async def test_nonstream_reasoning_off_no_reasoning_content():
    async def fake_stream():
        yield {"type": "reasoning-delta", "text": "First, I need to"}
        yield {"type": "reasoning-delta", "text": " break this down"}
        yield {"type": "text-delta", "text": "Answer: 42"}
        yield {"type": "finish", "finishReason": "end_turn", "totalUsage": {"inputTokens": 5, "outputTokens": 2}}

    result = await collect_and_translate_nonstream(fake_stream(), "deepseek-v4", time.time(), reasoning_effort="off")
    assert result.choices[0].message.reasoning_content is None
    assert result.choices[0].message.content == "Answer: 42"


@pytest.mark.asyncio
async def test_stream_reasoning_high_passes_through():
    async def fake_stream():
        yield {"type": "reasoning-delta", "text": "Let me think"}
        yield {"type": "text-delta", "text": "Answer"}
        yield {"type": "finish", "finishReason": "end_turn", "totalUsage": {"inputTokens": 5, "outputTokens": 3}}

    chunks = []
    async for chunk in translate_stream(fake_stream(), "deepseek-v4", time.time(), reasoning_effort="high"):
        chunks.append(chunk)

    assert '"reasoning_content":"Let me think"' in chunks[0]


@pytest.mark.asyncio
async def test_nonstream_reasoning_high_passes_through():
    async def fake_stream():
        yield {"type": "reasoning-delta", "text": "Step by step"}
        yield {"type": "text-delta", "text": "Answer"}
        yield {"type": "finish", "finishReason": "end_turn", "totalUsage": {"inputTokens": 5, "outputTokens": 2}}

    result = await collect_and_translate_nonstream(fake_stream(), "deepseek-v4", time.time(), reasoning_effort="high")
    assert result.choices[0].message.reasoning_content == "Step by step"


@pytest.mark.asyncio
async def test_nonstream_empty_raises_adapter_error():
    """No visible content and no tool_calls raises AdapterError(502)."""

    async def fake_stream():
        yield {"type": "finish", "finishReason": "end_turn", "totalUsage": {"inputTokens": 0, "outputTokens": 0}}

    with pytest.raises(AdapterError) as exc:
        await collect_and_translate_nonstream(fake_stream(), "deepseek-v4", time.time())
    assert exc.value.status_code == 502
    assert exc.value.message == "Upstream model returned an empty response"


@pytest.mark.asyncio
async def test_nonstream_reasoning_only_returns_content():
    """reasoning_content without content/tool_calls is returned as content."""

    async def fake_stream():
        yield {"type": "reasoning-delta", "text": "Let me think"}
        yield {"type": "finish", "finishReason": "end_turn", "totalUsage": {"inputTokens": 0, "outputTokens": 0}}

    resp = await collect_and_translate_nonstream(fake_stream(), "deepseek-v4", time.time())
    assert resp.choices[0].message.content == "Let me think"
    assert resp.choices[0].message.reasoning_content is None


@pytest.mark.asyncio
async def test_nonstream_reasoning_only_with_tools_raises_empty_error():
    """With tools available, thinking-only output should retry instead of ending the agent turn."""

    async def fake_stream():
        yield {"type": "reasoning-delta", "text": "Now I need to read files"}
        yield {"type": "finish", "finishReason": "end_turn", "totalUsage": {"inputTokens": 1, "outputTokens": 1}}

    with pytest.raises(AdapterError) as exc:
        await collect_and_translate_nonstream(fake_stream(), "deepseek-v4", time.time(), tools_available=True)
    assert exc.value.status_code == 502
    assert exc.value.message == "Upstream model returned an empty response"


@pytest.mark.asyncio
async def test_nonstream_error_event_raises_mapped_error():
    """Upstream error event is not translated to successful stop."""

    async def fake_stream():
        yield {"type": "error", "error": {"message": "Model overloaded", "statusCode": 503}}

    with pytest.raises(AdapterError) as exc:
        await collect_and_translate_nonstream(fake_stream(), "deepseek-v4", time.time())
    assert exc.value.message == "Model overloaded"
    assert exc.value.status_code == 502
    assert exc.value.original_status == 503


@pytest.mark.asyncio
async def test_nonstream_error_event_without_status_uses_502():
    async def fake_stream():
        yield {"type": "error", "error": {"message": "Unknown upstream failure", "statusCode": None}}

    with pytest.raises(AdapterError) as exc:
        await collect_and_translate_nonstream(fake_stream(), "deepseek-v4", time.time())
    assert exc.value.status_code == 502
    assert exc.value.message == "Unknown upstream failure"


@pytest.mark.asyncio
async def test_nonstream_tool_calls_with_end_turn_finish_reason():
    """Non-streaming tool-only response gets tool_calls finish_reason even when upstream says end_turn."""

    async def fake_stream():
        yield {"type": "tool-call", "toolCallId": "call_1", "toolName": "read", "input": {"path": "/tmp/x"}}
        yield {"type": "finish", "finishReason": "end_turn", "totalUsage": {"inputTokens": 5, "outputTokens": 2}}

    result = await collect_and_translate_nonstream(fake_stream(), "deepseek-v4", time.time())
    assert len(result.choices[0].message.tool_calls) == 1
    assert result.choices[0].finish_reason == "tool_calls"


@pytest.mark.asyncio
async def test_nonstream_reasoning_off_empty_still_raises():
    """reasoning_effort=off filters reasoning, leaving nothing, so it still raises."""

    async def fake_stream():
        yield {"type": "reasoning-delta", "text": "Some thinking"}
        yield {"type": "finish", "finishReason": "end_turn", "totalUsage": {"inputTokens": 1, "outputTokens": 1}}

    with pytest.raises(AdapterError) as exc:
        await collect_and_translate_nonstream(fake_stream(), "deepseek-v4", time.time(), reasoning_effort="off")
    assert exc.value.status_code == 502
    assert exc.value.message == "Upstream model returned an empty response"


@pytest.mark.asyncio
async def test_stream_empty_emits_error_payload():
    """Streaming empty response emits error SSE then [DONE]."""

    async def fake_stream():
        yield {"type": "finish", "finishReason": "end_turn", "totalUsage": {"inputTokens": 0, "outputTokens": 0}}

    chunks = []
    async for chunk in translate_stream(fake_stream(), "deepseek-v4", time.time()):
        chunks.append(chunk)

    assert len(chunks) == 2  # error + [DONE]
    # First chunk should be an error payload
    assert chunks[0].startswith("data: ")
    # Parse the payload to check it has an error
    payload = json.loads(chunks[0][6:])
    assert "error" in payload
    assert payload["error"]["message"] == "Upstream model returned an empty response"
    assert payload["error"]["type"] == "api_error"
    assert payload["error"]["code"] == 502
    assert chunks[1] == "data: [DONE]\n\n"


@pytest.mark.asyncio
async def test_stream_empty_text_delta_emits_error_payload():
    """An empty text-delta does not count as visible output."""

    async def fake_stream():
        yield {"type": "text-delta", "text": ""}
        yield {"type": "finish", "finishReason": "end_turn", "totalUsage": {"inputTokens": 1, "outputTokens": 0}}

    chunks = []
    async for chunk in translate_stream(fake_stream(), "deepseek-v4", time.time()):
        chunks.append(chunk)

    assert len(chunks) == 2
    payload = json.loads(chunks[0][6:])
    assert payload["error"]["message"] == "Upstream model returned an empty response"
    assert chunks[1] == "data: [DONE]\n\n"


@pytest.mark.asyncio
async def test_stream_reasoning_only_returns_content():
    """Streaming reasoning-only (no text, no tool_calls) returns reasoning as content at finish."""

    async def fake_stream():
        yield {"type": "reasoning-delta", "text": "I am thinking"}
        yield {"type": "finish", "finishReason": "end_turn", "totalUsage": {"inputTokens": 1, "outputTokens": 0}}

    chunks = []
    async for chunk in translate_stream(fake_stream(), "deepseek-v4", time.time()):
        chunks.append(chunk)

    # reasoning-delta → content fallback → finish → [DONE]
    assert len(chunks) == 4
    assert '"reasoning_content":"I am thinking"' in chunks[0]
    assert '"content":"I am thinking"' in chunks[1]
    assert '"finish_reason":"stop"' in chunks[2]
    assert chunks[3] == "data: [DONE]\n\n"


@pytest.mark.asyncio
async def test_stream_reasoning_only_with_tools_emits_empty_error():
    """With tools available, reasoning-only streaming output is treated as empty for retry."""

    async def fake_stream():
        yield {"type": "reasoning-delta", "text": "Now I need to update files"}
        yield {"type": "finish", "finishReason": "end_turn", "totalUsage": {"inputTokens": 1, "outputTokens": 1}}

    chunks = []
    async for chunk in translate_stream(fake_stream(), "deepseek-v4", time.time(), tools_available=True):
        chunks.append(chunk)

    assert '"reasoning_content":"Now I need to update files"' in chunks[0]
    payload = json.loads(chunks[1][6:])
    assert payload["error"]["message"] == "Upstream model returned an empty response"
    assert chunks[2] == "data: [DONE]\n\n"


@pytest.mark.asyncio
async def test_stream_with_retry_retries_reasoning_only_tool_turn():
    """A thinking-only tool turn should automatically retry and surface the second attempt's tool call."""

    attempts = 0

    def generate():
        nonlocal attempts
        attempts += 1

        async def fake_stream():
            if attempts == 1:
                yield {"type": "reasoning-delta", "text": "Now I need to update files"}
                yield {"type": "finish", "finishReason": "end_turn", "totalUsage": {"inputTokens": 1, "outputTokens": 1}}
            else:
                yield {"type": "tool-call", "toolCallId": "call_1", "toolName": "read", "input": {"path": "/tmp/x"}}
                yield {"type": "finish", "finishReason": "tool_calls", "totalUsage": {"inputTokens": 1, "outputTokens": 1}}

        return fake_stream()

    chunks = []
    async for chunk in _stream_with_retry(generate, "deepseek-v4", time.time(), tools_available=True):
        chunks.append(chunk)

    assert attempts == 2
    assert any('"tool_calls"' in chunk for chunk in chunks)
    assert not any('"error"' in chunk for chunk in chunks)
    assert not any("Now I need to update files" in chunk for chunk in chunks)


@pytest.mark.asyncio
async def test_stream_with_retry_does_not_retry_after_visible_output():
    """Once visible output has been sent, retrying would mix two attempts in one client stream."""

    attempts = 0

    def generate():
        nonlocal attempts
        attempts += 1

        async def fake_stream():
            if attempts == 1:
                yield {"type": "text-delta", "text": "Visible output"}
                yield {
                    "type": "error",
                    "error": {"message": "Upstream model returned an empty response", "statusCode": 502},
                }
            else:
                yield {"type": "text-delta", "text": "Second attempt"}
                yield {"type": "finish", "finishReason": "end_turn", "totalUsage": {"inputTokens": 1, "outputTokens": 1}}

        return fake_stream()

    chunks = []
    async for chunk in _stream_with_retry(generate, "deepseek-v4", time.time(), tools_available=True):
        chunks.append(chunk)

    assert attempts == 1
    assert any('"content":"Visible output"' in chunk for chunk in chunks)
    assert any('"error"' in chunk for chunk in chunks)
    assert not any("Second attempt" in chunk for chunk in chunks)


@pytest.mark.asyncio
async def test_stream_error_event_emits_error_payload():
    """Upstream 'error' event emits error SSE payload, not finish."""

    async def fake_stream():
        yield {"type": "error", "error": {"message": "Server error", "statusCode": 503}}

    chunks = []
    async for chunk in translate_stream(fake_stream(), "deepseek-v4", time.time()):
        chunks.append(chunk)

    assert len(chunks) == 2
    payload = json.loads(chunks[0][6:])
    assert "error" in payload
    assert payload["error"]["message"] == "Server error"
    assert chunks[1] == "data: [DONE]\n\n"


@pytest.mark.asyncio
async def test_stream_error_event_without_status_uses_502():
    async def fake_stream():
        yield {"type": "error", "error": {"message": "Unknown upstream failure", "statusCode": None}}

    chunks = []
    async for chunk in translate_stream(fake_stream(), "deepseek-v4", time.time()):
        chunks.append(chunk)

    payload = json.loads(chunks[0][6:])
    assert payload["error"]["message"] == "Unknown upstream failure"
    assert payload["error"]["code"] == 502


@pytest.mark.asyncio
async def test_stream_reasoning_off_empty_emits_error():
    """Streaming with reasoning_effort=off where only reasoning_deltas exist emits error."""

    async def fake_stream():
        yield {"type": "reasoning-delta", "text": "Thinking..."}
        yield {"type": "finish", "finishReason": "end_turn", "totalUsage": {"inputTokens": 1, "outputTokens": 0}}

    chunks = []
    async for chunk in translate_stream(fake_stream(), "deepseek-v4", time.time(), reasoning_effort="off"):
        chunks.append(chunk)

    assert len(chunks) == 2
    payload = json.loads(chunks[0][6:])
    assert "error" in payload


@pytest.mark.asyncio
async def test_nonstream_tool_calls_with_content_no_empty_error():
    """Tool-call + content is not empty."""

    async def fake_stream():
        yield {"type": "text-delta", "text": "Here you go"}
        yield {"type": "tool-call", "toolCallId": "call_1", "toolName": "read", "input": {"path": "/tmp/x"}}
        yield {"type": "finish", "finishReason": "end_turn", "totalUsage": {"inputTokens": 5, "outputTokens": 2}}

    result = await collect_and_translate_nonstream(fake_stream(), "deepseek-v4", time.time())
    assert result.choices[0].message.content == "Here you go"
    assert len(result.choices[0].message.tool_calls) == 1


@pytest.mark.asyncio
async def test_stream_contentful_response_not_empty():
    """Regular streaming response with content is not impacted."""

    async def fake_stream():
        yield {"type": "text-delta", "text": "Hello"}
        yield {"type": "finish", "finishReason": "end_turn", "totalUsage": {"inputTokens": 1, "outputTokens": 1}}

    chunks = []
    async for chunk in translate_stream(fake_stream(), "deepseek-v4", time.time()):
        chunks.append(chunk)

    assert len(chunks) == 3  # text + finish + [DONE]
    assert '"content":"Hello"' in chunks[0]
