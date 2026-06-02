import httpx
import pytest
from cc_adapter.command_code.client import CommandCodeClient, _parse_sse_line
from cc_adapter.core.errors import AuthenticationError, UpstreamError


@pytest.mark.asyncio
async def test_client_requires_api_key():
    client = CommandCodeClient(base_url="https://api.commandcode.ai", api_key="")
    with pytest.raises(AuthenticationError, match="CC_ADAPTER_CC_API_KEY is not configured"):
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


def test_client_logs_invalid_lines():
    """Invalid lines are skipped silently (logged at debug level)."""
    lines = [
        "not json at all",
        'data: {"type":"valid"}',
        "{broken",
    ]

    results = [_parse_sse_line(raw) for raw in lines]
    # non-json lines return None; valid line returns parsed dict
    assert results[0] is None
    assert results[1] is not None
    assert results[2] is None


def test_client_rejects_non_object_json():
    """A valid JSON value that is not an event object is ignored."""
    assert _parse_sse_line('data: ["not", "an", "event"]') is None


@pytest.mark.asyncio
async def test_client_reuses_injected_http_client():
    injected = httpx.AsyncClient()
    client = CommandCodeClient(base_url="https://api.commandcode.ai", api_key="test", http_client=injected)
    assert client._client() is injected
    assert client._client() is injected


@pytest.mark.asyncio
async def test_client_connect_error_maps_to_upstream_error():
    from unittest.mock import patch

    with patch.object(httpx.AsyncClient, "stream") as mock_stream:
        mock_stream.side_effect = httpx.ConnectError("Connection refused")
        client = CommandCodeClient(base_url="https://api.commandcode.ai", api_key="test")
        with pytest.raises(UpstreamError, match="Command Code API request failed: ConnectError"):
            async for _ in client.generate({"params": {"model": "test", "messages": []}}):
                pass


@pytest.mark.asyncio
async def test_client_aclose_cleans_up_owned_client():
    client = CommandCodeClient(base_url="https://api.commandcode.ai", api_key="test")
    http_client = client._client()
    assert not http_client.is_closed
    await client.aclose()
    assert http_client.is_closed


@pytest.mark.asyncio
async def test_client_aclose_does_not_close_injected_client():
    injected = httpx.AsyncClient()
    client = CommandCodeClient(base_url="https://api.commandcode.ai", api_key="test", http_client=injected)
    await client.aclose()
    assert not injected.is_closed


def test_client_generates_stable_session_id():
    """Session ID is stable per client instance, matches sess_<16hex> format."""
    client = CommandCodeClient(base_url="https://api.commandcode.ai", api_key="test")
    sid = client._session_id
    assert sid.startswith("sess_")
    assert len(sid) == len("sess_") + 16
    assert client._session_id == sid  # idempotent, no regeneration


@pytest.mark.asyncio
async def test_generate_injects_session_id_in_headers():
    """generate() adds x-session-id header from client._session_id."""
    from unittest.mock import patch, AsyncMock

    async def fake_lines():
        yield '{"type":"finish","finishReason":"end_turn"}'

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__.return_value = mock_ctx
    mock_ctx.is_error = False
    mock_ctx.status_code = 200
    mock_ctx.aiter_lines = fake_lines

    with patch.object(httpx.AsyncClient, "stream", return_value=mock_ctx) as mock_stream:
        client = CommandCodeClient(base_url="https://api.commandcode.ai", api_key="test")
        async for _ in client.generate({"params": {"model": "test", "messages": []}}):
            pass
        _, kwargs = mock_stream.call_args
        assert kwargs["headers"]["x-session-id"] == client._session_id
