import json

import pytest
import respx
from httpx import ASGITransport, AsyncClient, Response as HttpxResponse

from cc_adapter.main import app
from cc_adapter.core.config import AppConfig
from cc_adapter.core import runtime


@pytest.fixture(autouse=True)
def _clean_runtime():
    saved_config = runtime._config
    saved_client = runtime._cc_client
    yield
    runtime._config = saved_config
    runtime._cc_client = saved_client


DEEPSEEK_SSE_RESPONSE = (
    b"event: message_start\n"
    b'data: {"type":"message_start","message":{"id":"msg_1","model":"deepseek-v4-flash","role":"assistant","content":[],"stop_reason":null,"usage":{"input_tokens":10,"output_tokens":0}}}\n\n'
    b"event: content_block_start\n"
    b'data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}\n\n'
    b"event: content_block_delta\n"
    b'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hello from DeepSeek"}}\n\n'
    b"event: content_block_stop\n"
    b'data: {"type":"content_block_stop","index":0}\n\n'
    b"event: message_delta\n"
    b'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":5}}\n\n'
    b"event: message_stop\n"
    b'data: {"type":"message_stop"}\n\n'
)


@pytest.mark.asyncio
async def test_stream_uses_cc_when_deepseek_enabled_without_web_search_tool():
    cfg = AppConfig(cc_api_key="test-key", web_search_provider="deepseek", deepseek_api_key="sk-test")
    runtime._config = cfg
    runtime._cc_client = None

    async with respx.mock(assert_all_called=False) as respx_mock:
        deepseek_route = respx_mock.post("https://api.deepseek.com/anthropic/v1/messages").mock(
            return_value=HttpxResponse(200, content=DEEPSEEK_SSE_RESPONSE)
        )
        cc_route = respx_mock.post("https://api.commandcode.ai/alpha/generate").mock(
            return_value=HttpxResponse(
                200,
                text=(
                    'data: {"type":"text-delta","text":"Hello from CC"}\n\n'
                    'data: {"type":"finish","finishReason":"end_turn","totalUsage":{"inputTokens":10,"outputTokens":5}}\n\n'
                ),
            )
        )
        respx_mock.get("https://registry.npmjs.org/command-code/latest").mock(
            return_value=HttpxResponse(200, json={"version": "0.25.2"})
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/v1/messages",
                json={
                    "model": "deepseek-v4-flash",
                    "max_tokens": 100,
                    "messages": [{"role": "user", "content": "hello"}],
                    "stream": True,
                },
            )

    assert resp.status_code == 200
    assert "Hello from CC" in resp.text
    assert cc_route.called
    assert not deepseek_route.called


@pytest.mark.asyncio
async def test_stream_forward_does_not_write_passthrough_log_file(tmp_path, monkeypatch):
    cfg = AppConfig(cc_api_key="test-key", web_search_provider="deepseek", deepseek_api_key="sk-test")
    runtime._config = cfg
    runtime._cc_client = None
    monkeypatch.chdir(tmp_path)

    async with respx.mock(assert_all_called=False) as respx_mock:
        deepseek_route = respx_mock.post("https://api.deepseek.com/anthropic/v1/messages").mock(
            return_value=HttpxResponse(200, content=DEEPSEEK_SSE_RESPONSE)
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/v1/messages",
                json={
                    "model": "deepseek-v4-flash",
                    "max_tokens": 100,
                    "messages": [{"role": "user", "content": "hello"}],
                    "stream": True,
                    "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 1}],
                },
            )

    assert resp.status_code == 200
    assert deepseek_route.called
    assert not (tmp_path / "logs").exists()


@pytest.mark.asyncio
async def test_stream_forwards_server_web_search_tool_shape_to_deepseek():
    cfg = AppConfig(cc_api_key="test-key", web_search_provider="deepseek", deepseek_api_key="sk-test")
    runtime._config = cfg
    runtime._cc_client = None

    async with respx.mock(assert_all_called=False) as respx_mock:
        deepseek_route = respx_mock.post("https://api.deepseek.com/anthropic/v1/messages").mock(
            return_value=HttpxResponse(200, content=DEEPSEEK_SSE_RESPONSE)
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/v1/messages",
                json={
                    "model": "deepseek-v4-flash",
                    "max_tokens": 100,
                    "messages": [{"role": "user", "content": "search the web for current news"}],
                    "stream": True,
                    "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}],
                    "tool_choice": {"type": "auto"},
                    "top_p": 0.8,
                    "stop_sequences": ["STOP"],
                },
            )

    assert resp.status_code == 200
    assert deepseek_route.called
    forwarded_body = json.loads(deepseek_route.calls.last.request.content)
    assert forwarded_body["tools"] == [{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}]
    assert forwarded_body["tool_choice"] == {"type": "auto"}
    assert forwarded_body["top_p"] == 0.8
    assert forwarded_body["stop_sequences"] == ["STOP"]


@pytest.mark.asyncio
async def test_stream_uses_configured_web_search_model_for_deepseek():
    cfg = AppConfig(
        cc_api_key="test-key",
        web_search_provider="deepseek",
        deepseek_api_key="sk-test",
        web_search_model="deepseek-v4-pro",
    )
    runtime._config = cfg
    runtime._cc_client = None

    async with respx.mock(assert_all_called=False) as respx_mock:
        deepseek_route = respx_mock.post("https://api.deepseek.com/anthropic/v1/messages").mock(
            return_value=HttpxResponse(200, content=DEEPSEEK_SSE_RESPONSE)
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/v1/messages",
                json={
                    "model": "deepseek-v4-flash",
                    "max_tokens": 100,
                    "messages": [{"role": "user", "content": "search the web"}],
                    "stream": True,
                    "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 1}],
                },
            )

    assert resp.status_code == 200
    assert deepseek_route.called
    forwarded_body = json.loads(deepseek_route.calls.last.request.content)
    assert forwarded_body["model"] == "deepseek-v4-pro"


@pytest.mark.asyncio
async def test_nonstream_forwards_to_deepseek():
    cfg = AppConfig(cc_api_key="test-key", web_search_provider="deepseek", deepseek_api_key="sk-test")
    runtime._config = cfg
    runtime._cc_client = None

    deepseek_json = {
        "id": "msg_deepseek_1",
        "type": "message",
        "role": "assistant",
        "model": "deepseek-v4-flash",
        "content": [{"type": "text", "text": "Non-stream response"}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }

    async with respx.mock(assert_all_called=False) as respx_mock:
        deepseek_route = respx_mock.post("https://api.deepseek.com/anthropic/v1/messages").mock(
            return_value=HttpxResponse(200, json=deepseek_json)
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/v1/messages",
                json={
                    "model": "deepseek-v4-flash",
                    "max_tokens": 100,
                    "messages": [{"role": "user", "content": "hello"}],
                    "stream": False,
                    "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 1}],
                },
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["content"][0]["text"] == "Non-stream response"
    assert deepseek_route.called


@pytest.mark.asyncio
async def test_disabled_still_goes_to_cc():
    cfg = AppConfig(cc_api_key="test-key", web_search_provider="", deepseek_api_key="")
    runtime._config = cfg
    runtime._cc_client = None

    async with respx.mock(assert_all_called=False) as respx_mock:
        cc_route = respx_mock.post("https://api.commandcode.ai/alpha/generate").mock(
            return_value=HttpxResponse(
                200,
                text=(
                    'data: {"type":"text-delta","text":"Hello"}\n\n'
                    'data: {"type":"finish","finishReason":"end_turn","totalUsage":{"inputTokens":10,"outputTokens":5}}\n\n'
                ),
            )
        )
        respx_mock.get("https://registry.npmjs.org/command-code/latest").mock(
            return_value=HttpxResponse(200, json={"version": "0.25.2"})
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/v1/messages",
                json={
                    "model": "claude-sonnet-4-6",
                    "max_tokens": 100,
                    "messages": [{"role": "user", "content": "hello"}],
                    "stream": True,
                },
            )

    assert resp.status_code == 200
    assert cc_route.called


@pytest.mark.asyncio
async def test_server_tool_without_deepseek_forwarding_returns_400():
    cfg = AppConfig(cc_api_key="test-key", web_search_provider="", deepseek_api_key="")
    runtime._config = cfg
    runtime._cc_client = None

    async with respx.mock(assert_all_called=False) as respx_mock:
        cc_route = respx_mock.post("https://api.commandcode.ai/alpha/generate").mock(
            return_value=HttpxResponse(200, text='data: {"type":"text-delta","text":"unexpected"}\n\n')
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/v1/messages",
                json={
                    "model": "claude-sonnet-4-6",
                    "max_tokens": 100,
                    "messages": [{"role": "user", "content": "search"}],
                    "stream": False,
                    "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 1}],
                },
            )

    assert resp.status_code == 400
    assert "server tool" in resp.json()["error"]["message"]
    assert not cc_route.called


@pytest.mark.asyncio
async def test_deepseek_error_returns_error_in_stream():
    cfg = AppConfig(cc_api_key="test-key", web_search_provider="deepseek", deepseek_api_key="sk-test")
    runtime._config = cfg
    runtime._cc_client = None

    async with respx.mock(assert_all_called=False) as respx_mock:
        respx_mock.post("https://api.deepseek.com/anthropic/v1/messages").mock(
            return_value=HttpxResponse(500, text="Internal error")
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/v1/messages",
                json={
                    "model": "deepseek-v4-flash",
                    "max_tokens": 100,
                    "messages": [{"role": "user", "content": "hello"}],
                    "stream": True,
                    "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 1}],
                },
            )

    assert resp.status_code == 200
    assert "DeepSeek API error" in resp.text
