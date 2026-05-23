import pytest
from httpx import ASGITransport, AsyncClient
from cc_adapter.main import app
from cc_adapter.core.auth import set_password, generate_token
from cc_adapter.core.runtime import init as admin_state_init
from cc_adapter.core.config import AppConfig
from cc_adapter.command_code.client import CommandCodeClient
from cc_adapter.core.log_buffer import clear as clear_log_buffer, append as append_log


@pytest.fixture(autouse=True)
def setup_logs():
    cfg = AppConfig(admin_password="admin123")
    client = CommandCodeClient(base_url=cfg.cc_base_url, api_key="")
    admin_state_init(cfg, client)
    set_password("admin123")
    clear_log_buffer()


@pytest.mark.asyncio
async def test_logs_requires_auth():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/admin/api/logs")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_logs_returns_entries():
    append_log({"timestamp": "2026-05-23T14:30:45", "level": "INFO", "event": "test.event", "msg": "hello"})
    append_log({"timestamp": "2026-05-23T14:30:46", "level": "ERROR", "event": "test.error", "msg": "fail"})

    token = generate_token()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/admin/api/logs", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "entries" in data
    assert "total_in_buffer" in data
    assert len(data["entries"]) == 2
    assert data["total_in_buffer"] == 2


@pytest.mark.asyncio
async def test_logs_level_filter():
    append_log({"timestamp": "2026-05-23T14:30:45", "level": "DEBUG", "event": "debug.event"})
    append_log({"timestamp": "2026-05-23T14:30:46", "level": "INFO", "event": "info.event"})
    append_log({"timestamp": "2026-05-23T14:30:47", "level": "ERROR", "event": "error.event"})

    token = generate_token()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/admin/api/logs?level=WARNING", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["entries"]) == 1
    assert data["entries"][0]["event"] == "error.event"


@pytest.mark.asyncio
async def test_logs_search_filter():
    append_log({"timestamp": "2026-05-23T14:30:45", "level": "INFO", "event": "auth.failed", "reason": "bad token"})
    append_log({"timestamp": "2026-05-23T14:30:46", "level": "INFO", "event": "http.done", "method": "GET"})

    token = generate_token()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/admin/api/logs?search=auth", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["entries"]) == 1
    assert data["entries"][0]["event"] == "auth.failed"


@pytest.mark.asyncio
async def test_logs_empty_buffer():
    token = generate_token()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/admin/api/logs", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["entries"] == []
    assert data["total_in_buffer"] == 0


@pytest.mark.asyncio
async def test_reasoning_effort_public():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/admin/api/reasoning-effort")
    assert resp.status_code == 200
    data = resp.json()
    assert "model_reasoning_efforts" in data
