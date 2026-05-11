from __future__ import annotations

from httpx import ASGITransport, AsyncClient
import pytest

from cc_adapter.main import app

TRANSPORT = ASGITransport(app=app)


@pytest.mark.asyncio
async def test_v1_models_returns_all_19_models():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as client:
        resp = await client.get("/v1/models")

    assert resp.status_code == 200
    body = resp.json()
    assert body["object"] == "list"
    assert isinstance(body["data"], list)
    assert len(body["data"]) == 19
    for model in body["data"]:
        assert model["object"] == "model"
        assert "id" in model
        assert "created" in model
        assert "owned_by" in model


@pytest.mark.asyncio
async def test_v1_models_contains_known_model():
    async with AsyncClient(transport=TRANSPORT, base_url="http://test") as client:
        resp = await client.get("/v1/models")

    ids = {m["id"] for m in resp.json()["data"]}
    assert "deepseek/deepseek-v4-flash" in ids
    assert "stepfun/Step-3.5-Flash" in ids
    assert "claude-sonnet-4-6" in ids
    assert "gpt-5.4" in ids
