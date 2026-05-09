import pytest
from httpx import ASGITransport, AsyncClient
from cc_adapter.main import app


@pytest.mark.asyncio
async def test_anthropic_invalid_body():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/messages",
            json={"model": "test"},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_anthropic_no_api_key():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/messages",
            json={"model": "claude-sonnet-4-6", "max_tokens": 100, "messages": [{"role": "user", "content": "hi"}]},
        )
    assert resp.status_code in (401, 502)


@pytest.mark.asyncio
async def test_anthropic_health():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
