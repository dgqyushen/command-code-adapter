import pytest
from httpx import AsyncClient, ASGITransport
from cc_adapter.main import app


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_health_endpoint(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_nonstream_unsupported_params_logged(client):
    """Request with unsupported params should not error."""
    payload = {
        "model": "claude-sonnet-4-6",
        "messages": [{"role": "user", "content": "hi"}],
        "top_p": 0.9,
        "stream": False,
    }
    # This will likely return 502 because CC_ADAPTER_CC_API_KEY is not set in test,
    # but it should NOT crash — it should go through the translator
    response = await client.post("/v1/chat/completions", json=payload)
    assert response.status_code in (200, 401, 502)


@pytest.mark.asyncio
async def test_chat_completions_invalid_body(client):
    response = await client.post(
        "/v1/chat/completions",
        json={"model": "test"},  # missing messages
    )
    assert response.status_code == 422  # validation error


@pytest.mark.asyncio
async def test_stream_endpoint(client):
    payload = {
        "model": "claude-sonnet-4-6",
        "messages": [{"role": "user", "content": "hi"}],
        "stream": True,
    }
    response = await client.post("/v1/chat/completions", json=payload)
    # May fail if no API key, but should return proper error
    assert response.status_code in (200, 401, 502)
