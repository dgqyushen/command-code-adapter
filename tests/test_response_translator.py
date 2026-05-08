import time

import pytest
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

    result = await collect_and_translate_nonstream(
        fake_stream(), "deepseek-v4", time.time(), reasoning_effort="off"
    )
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

    result = await collect_and_translate_nonstream(
        fake_stream(), "deepseek-v4", time.time(), reasoning_effort="high"
    )
    assert result.choices[0].message.reasoning_content == "Step by step"
