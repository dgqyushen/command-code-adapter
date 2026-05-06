import pytest
from cc_adapter.translator.response import collect_and_translate_nonstream, translate_stream


@pytest.mark.asyncio
async def test_nonstream_simple_text():
    async def fake_stream():
        yield {"type": "text-delta", "text": "Hello"}
        yield {"type": "text-delta", "text": " world"}
        yield {"type": "finish", "finishReason": "end_turn", "totalUsage": {"inputTokens": 10, "outputTokens": 5}}

    result = await collect_and_translate_nonstream(fake_stream(), "claude-sonnet-4-6")
    assert result.choices[0].message.content == "Hello world"
    assert result.choices[0].finish_reason == "stop"
    assert result.usage.prompt_tokens == 10
    assert result.usage.completion_tokens == 5


@pytest.mark.asyncio
async def test_nonstream_tool_calls():
    async def fake_stream():
        yield {"type": "tool-call", "toolCallId": "call_1", "toolName": "read_file", "args": {"path": "/tmp/x"}}
        yield {"type": "finish", "finishReason": "tool_calls", "totalUsage": {"inputTokens": 5, "outputTokens": 2}}

    result = await collect_and_translate_nonstream(fake_stream(), "gpt-5.4")
    assert len(result.choices[0].message.tool_calls) == 1
    assert result.choices[0].message.tool_calls[0].function.name == "read_file"
    assert result.choices[0].finish_reason == "tool_calls"


@pytest.mark.asyncio
async def test_stream_output():
    async def fake_stream():
        yield {"type": "text-delta", "text": "Hi"}
        yield {"type": "finish", "finishReason": "end_turn", "totalUsage": {"inputTokens": 1, "outputTokens": 1}}

    chunks = []
    async for chunk in translate_stream(fake_stream(), "claude-sonnet-4-6"):
        chunks.append(chunk)

    assert len(chunks) == 3  # text-delta + finish + [DONE]
    assert 'data: {"id":"chatcmpl-' in chunks[0]
    assert '"content":"Hi"' in chunks[0]
    assert chunks[2] == "data: [DONE]\n\n"
