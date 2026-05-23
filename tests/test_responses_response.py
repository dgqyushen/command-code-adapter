import json
import time

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from cc_adapter.core.errors import AdapterError
from cc_adapter.providers.openai.responses_response import (
    _ResponsesStreamState,
    _sse,
    translate_responses_stream,
    collect_and_translate_responses_nonstream,
)


def _make_cc_event(event_type: str, **kwargs):
    return {"type": event_type, **kwargs}


class TestSse:
    def test_sse_format(self):
        result = _sse("test.event", {"foo": "bar"})
        assert "event: test.event" in result
        assert "data:" in result
        assert '"type": "test.event"' in result
        assert '"foo": "bar"' in result


class TestResponsesStreamState:
    def test_bootstrap_emitted_once(self):
        state = _ResponsesStreamState("resp_1", "test-model", 1234567890.0)

        assert not state.bootstrap_done

        chunks = list(state.process_event(_make_cc_event("reasoning-delta", text="hello")))
        bootstrap_events = [c for c in chunks if "response.created" in c or "response.in_progress" in c]
        assert len(bootstrap_events) == 2

    def test_close_current_item_reasoning(self):
        state = _ResponsesStreamState("resp_1", "test-model", 1234567890.0)
        state.set_current_item("reasoning", "rs_1")
        state.reasoning_buf.append("thinking...")

        chunks = list(state.close_current_item())
        assert len(chunks) == 2
        assert "response.content_part.done" in chunks[0]
        assert "response.output_item.done" in chunks[1]

    def test_close_current_item_text(self):
        state = _ResponsesStreamState("resp_1", "test-model", 1234567890.0)
        state.set_current_item("text", "msg_1")
        state.text_buf.append("hello world")

        chunks = list(state.close_current_item())
        assert len(chunks) == 3
        assert "response.content_part.done" in chunks[0]
        assert "response.output_text.done" in chunks[1]
        assert "response.output_item.done" in chunks[2]

    def test_close_current_item_fc(self):
        state = _ResponsesStreamState("resp_1", "test-model", 1234567890.0)
        state.set_current_item("fc", "fc_1")
        chunks = list(state.close_current_item())
        assert len(chunks) == 0

    def test_close_current_item_none(self):
        state = _ResponsesStreamState("resp_1", "test-model", 1234567890.0)
        chunks = list(state.close_current_item())
        assert len(chunks) == 0

    def test_process_reasoning_delta(self):
        state = _ResponsesStreamState("resp_1", "test-model", 1234567890.0)
        chunks = list(state.process_event(_make_cc_event("reasoning-delta", text="hello")))
        delta_events = [c for c in chunks if "response.reasoning_text.delta" in c]
        assert len(delta_events) == 1

    def test_process_reasoning_delta_switches_from_text(self):
        state = _ResponsesStreamState("resp_1", "test-model", 1234567890.0)
        list(state.process_event(_make_cc_event("text-delta", text="text output")))
        chunks = list(state.process_event(_make_cc_event("reasoning-delta", text="thinking")))
        text_done = [c for c in chunks if "response.output_item.done" in c]
        reasoning_added = [c for c in chunks if '"type": "reasoning"' in c and "output_item.added" in c]
        assert len(text_done) > 0
        assert len(reasoning_added) > 0

    def test_process_text_delta(self):
        state = _ResponsesStreamState("resp_1", "test-model", 1234567890.0)
        chunks = list(state.process_event(_make_cc_event("text-delta", text="hello world")))
        delta_events = [c for c in chunks if "response.output_text.delta" in c]
        assert len(delta_events) == 1

    def test_process_tool_call(self):
        state = _ResponsesStreamState("resp_1", "test-model", 1234567890.0)
        chunks = list(
            state.process_event(
                _make_cc_event("tool-call", toolName="read_file", toolCallId="call_abc123", input={"filePath": "/test"})
            )
        )
        add_events = [c for c in chunks if "response.output_item.added" in c]
        assert len(add_events) == 1

    def test_process_finish_with_content(self):
        state = _ResponsesStreamState("resp_1", "test-model", 1234567890.0)
        state.has_any_output = True
        state.text_buf.append("hello")
        state.text_item_id = "msg_1"
        state.set_current_item("text", "msg_1")

        chunks = list(state.process_event(_make_cc_event("finish", totalUsage={"input": 10, "output": 5})))
        complete_events = [c for c in chunks if "response.completed" in c]
        assert len(complete_events) == 1

    def test_process_finish_empty_raises(self):
        state = _ResponsesStreamState("resp_1", "test-model", 1234567890.0)
        with pytest.raises(AdapterError, match="empty response"):
            list(state.process_event(_make_cc_event("finish")))

    def test_process_error(self):
        state = _ResponsesStreamState("resp_1", "test-model", 1234567890.0)
        chunks = list(state.process_event(_make_cc_event("error", error={"message": "test error", "statusCode": 500})))
        error_events = [c for c in chunks if "event: error" in c or ('"type": "error"' in c)]
        assert len(error_events) == 1

    def test_finalize_with_content(self):
        state = _ResponsesStreamState("resp_1", "test-model", 1234567890.0)
        state.has_any_output = True
        chunks = list(state.finalize())
        assert len(chunks) == 1
        assert "error" in chunks[0]

    def test_finalize_empty_raises(self):
        state = _ResponsesStreamState("resp_1", "test-model", 1234567890.0)
        with pytest.raises(AdapterError, match="empty response"):
            list(state.finalize())


class TestTranslateResponsesStream:
    @pytest.mark.asyncio
    async def test_stream_with_text_and_finish(self):
        events = [
            _make_cc_event("text-delta", text="Hello "),
            _make_cc_event("text-delta", text="world"),
            _make_cc_event("finish", totalUsage={"input": 5, "output": 5}),
        ]

        async def mock_stream():
            for e in events:
                yield e

        output = []
        async for chunk in translate_responses_stream(mock_stream(), "test-model"):
            output.append(chunk)

        full = "".join(output)
        assert "response.created" in full
        assert "response.completed" in full
        assert "Hello " in full

    @pytest.mark.asyncio
    async def test_stream_empty_finish_raises(self):
        async def mock_stream():
            yield _make_cc_event("finish")

        with pytest.raises(AdapterError, match="empty response"):
            async for _ in translate_responses_stream(mock_stream(), "test-model"):
                pass

    @pytest.mark.asyncio
    async def test_stream_error_event(self):
        async def mock_stream():
            yield _make_cc_event("error", error={"message": "boom", "statusCode": 500})

        output = []
        async for chunk in translate_responses_stream(mock_stream(), "test-model"):
            output.append(chunk)

        full = "".join(output)
        assert "error" in full or '"type": "error"' in full

    @pytest.mark.asyncio
    async def test_stream_ends_without_finish(self):
        async def mock_stream():
            yield _make_cc_event("text-delta", text="partial")

        output = []
        async for chunk in translate_responses_stream(mock_stream(), "test-model"):
            output.append(chunk)

        full = "".join(output)
        assert "error" in full


class TestCollectResponsesNonstream:
    @pytest.mark.asyncio
    async def test_full_response(self):
        async def mock_stream():
            yield _make_cc_event("text-delta", text="Hello")
            yield _make_cc_event("reasoning-delta", text="thinking")
            yield _make_cc_event("finish", totalUsage={"input": 10, "output": 5})

        result = await collect_and_translate_responses_nonstream(mock_stream(), "test-model")
        assert result["status"] == "completed"
        assert result["model"] == "test-model"
        assert len(result["output"]) == 2  # reasoning + message

    @pytest.mark.asyncio
    async def test_tool_calls(self):
        async def mock_stream():
            yield _make_cc_event("tool-call", toolName="read_file", toolCallId="call_1", input={"filePath": "/f"})
            yield _make_cc_event("finish", totalUsage={"input": 10, "output": 5})

        result = await collect_and_translate_responses_nonstream(mock_stream(), "test-model")
        assert result["status"] == "completed"
        assert len(result["output"]) == 1
        assert result["output"][0]["type"] == "function_call"

    @pytest.mark.asyncio
    async def test_empty_response_raises(self):
        async def mock_stream():
            yield _make_cc_event("finish")

        with pytest.raises(AdapterError, match="empty response"):
            await collect_and_translate_responses_nonstream(mock_stream(), "test-model")

    @pytest.mark.asyncio
    async def test_error_event_raises(self):
        async def mock_stream():
            yield _make_cc_event("error", error={"message": "upstream error", "statusCode": 500})

        with pytest.raises(AdapterError):
            await collect_and_translate_responses_nonstream(mock_stream(), "test-model")
