import pytest
from cc_adapter.client import CommandCodeClient, _parse_sse_line
from cc_adapter.errors import AuthenticationError


@pytest.mark.asyncio
async def test_client_requires_api_key():
    client = CommandCodeClient(base_url="https://api.commandcode.ai", api_key="")
    with pytest.raises(AuthenticationError, match="CC_API_KEY is not configured"):
        async for _ in client.generate({"params": {"model": "test", "messages": []}}):
            pass


@pytest.mark.parametrize(
    "raw_line, expected_type",
    [
        ('{"type":"text-delta","text":"hi"}', "text-delta"),
        ('data: {"type":"text-delta","text":"hi"}', "text-delta"),
        ('data:{"type":"text-delta","text":"hi"}', "text-delta"),
        ('{"type":"tool-call","toolName":"read","input":{}}', "tool-call"),
        ('data: {"type":"finish","finishReason":"end_turn"}', "finish"),
    ],
)
def test_client_bare_json_and_sse_lines(raw_line, expected_type):
    """Both bare JSON lines and 'data: {...}' lines are parsed."""
    parsed = _parse_sse_line(raw_line)
    assert parsed is not None
    assert parsed["type"] == expected_type


def test_client_ignores_done_and_empty_lines():
    """'data: [DONE]' and empty lines are ignored."""
    lines = [
        "",
        "   ",
        "data: [DONE]",
        "data:[DONE]",
        '{"type":"text-delta","text":"hello"}',
        "",
        "data: [DONE]",
    ]
    events = [_parse_sse_line(raw) for raw in lines]

    assert [event["type"] for event in events if event is not None] == ["text-delta"]


def test_client_logs_invalid_lines(caplog):
    """Invalid lines are logged with a short preview."""
    import logging

    caplog.set_level(logging.WARNING)
    lines = [
        "not json at all",
        'data: {"type":"valid"}',
        "{broken",
    ]

    for raw in lines:
        _parse_sse_line(raw)

    assert len(caplog.records) >= 1
    # Should mention the invalid content in the log message
    assert any("not json" in r.message for r in caplog.records)


def test_client_rejects_non_object_json(caplog):
    """A valid JSON value that is not an event object is ignored."""
    import logging

    caplog.set_level(logging.WARNING)

    assert _parse_sse_line('data: ["not", "an", "event"]') is None
    assert any("not a JSON object" in r.message for r in caplog.records)
