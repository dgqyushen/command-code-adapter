import pytest
from httpx import ASGITransport, AsyncClient
from cc_adapter.main import app
from cc_adapter.admin.auth import set_password
from cc_adapter.admin.router import router as admin_router
from cc_adapter.admin.state import init as admin_state_init
from cc_adapter.config import AppConfig
from cc_adapter.client import CommandCodeClient

app.include_router(admin_router)


@pytest.fixture(autouse=True)
def setup_auth():
    cfg = AppConfig()
    cfg.admin_password = "admin123"
    client = CommandCodeClient(base_url=cfg.cc_base_url, api_key=cfg.cc_api_key[0] if cfg.cc_api_key else "")
    admin_state_init(cfg, client)
    set_password("admin123")


@pytest.mark.asyncio
async def test_login_success():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/admin/api/login", json={"password": "admin123"})
    assert resp.status_code == 200
    data = resp.json()
    assert "token" in data


@pytest.mark.asyncio
async def test_login_failure():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/admin/api/login", json={"password": "wrong"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_config_requires_auth():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/admin/api/config")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_config_returns_fields():
    set_password("admin123")
    from cc_adapter.admin.auth import generate_token
    my_token = generate_token()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/admin/api/config", headers={"Authorization": f"Bearer {my_token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "cc_api_key" in data
    assert "cc_base_url" in data
    assert "host" in data
    assert "port" in data
    assert "log_level" in data


@pytest.mark.asyncio
async def test_update_config_uses_first_configured_key_for_client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from cc_adapter.admin.auth import generate_token
    from cc_adapter.admin.state import get_client, get_config

    my_token = generate_token()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.put(
            "/admin/api/config",
            json={"cc_api_key": '["user_one","user_two"]'},
            headers={"Authorization": f"Bearer {my_token}"},
        )

    assert resp.status_code == 200
    assert get_config().cc_api_key == ["user_one", "user_two"]
    assert get_client().api_key == "user_one"


@pytest.mark.asyncio
async def test_usage_query_returns_empty_when_no_keys():
    from cc_adapter.admin.state import init as admin_state_init, get_config
    from cc_adapter.admin.auth import generate_token

    cfg = get_config()
    cfg.cc_api_key = []
    my_token = generate_token()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/admin/api/usage/query", headers={"Authorization": f"Bearer {my_token}"})
    assert resp.status_code == 200
    assert resp.json() == []
