import pytest
from httpx import ASGITransport, AsyncClient
from cc_adapter.main import app
from cc_adapter.admin.auth import set_password, generate_token
from cc_adapter.admin.state import init as admin_state_init
from cc_adapter.config import AppConfig
from cc_adapter.client import CommandCodeClient


@pytest.fixture(autouse=True)
def setup():
    cfg = AppConfig(admin_password="admin123")
    client = CommandCodeClient(base_url=cfg.cc_base_url, api_key="")
    admin_state_init(cfg, client)
    set_password("admin123")


@pytest.mark.asyncio
async def test_admin_health():
    token = generate_token()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/admin/api/health", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "uptime" in data
    assert "version" in data


@pytest.mark.asyncio
async def test_list_models():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/admin/api/models")
    assert resp.status_code == 200
    data = resp.json()
    assert "models" in data
    assert len(data["models"]) > 0
    assert data["models"][0]["id"]


@pytest.mark.asyncio
async def test_ui_config():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/admin/api/ui-config")
    assert resp.status_code == 200
    data = resp.json()
    assert "default_model" in data


@pytest.mark.asyncio
async def test_raw_config_endpoints(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    token = generate_token()

    env_file = tmp_path / ".env"
    env_file.write_text("CC_ADAPTER_HOST=0.0.0.0\nCC_ADAPTER_PORT=8080\n")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/admin/api/config/raw", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert "CC_ADAPTER_HOST=0.0.0.0" in resp.json()["content"]


@pytest.mark.asyncio
async def test_reasoning_effort_config():
    token = generate_token()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/admin/api/reasoning-effort", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "max_prompt" in data
    assert "deepseek_v4_models" in data
