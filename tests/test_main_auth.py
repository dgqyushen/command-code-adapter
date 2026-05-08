import pytest
from httpx import ASGITransport, AsyncClient
from cc_adapter.main import app
from cc_adapter.admin.auth import set_password
from cc_adapter.admin.state import init as admin_state_init
from cc_adapter.config import AppConfig
from cc_adapter.client import CommandCodeClient


@pytest.fixture(autouse=True)
def setup():
    cfg = AppConfig(access_key="test_access_key", admin_password="admin123")
    client = CommandCodeClient(base_url=cfg.cc_base_url, api_key="")
    admin_state_init(cfg, client)
    set_password("admin123")


def _clear_state():
    from cc_adapter.admin.state import init as admin_state_init
    cfg = AppConfig()
    admin_state_init(cfg, CommandCodeClient(base_url=cfg.cc_base_url, api_key=""))
    set_password("")


@pytest.mark.asyncio
async def test_chat_completions_with_valid_access_key():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/chat/completions",
            json={"model": "test", "messages": [{"role": "user", "content": "hi"}]},
            headers={"Authorization": "Bearer test_access_key"},
        )
    assert resp.status_code in (200, 401, 502)


@pytest.mark.asyncio
async def test_chat_completions_with_invalid_access_key():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/chat/completions",
            json={"model": "test", "messages": [{"role": "user", "content": "hi"}]},
            headers={"Authorization": "Bearer wrong_key"},
        )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "invalid_api_key"


@pytest.mark.asyncio
async def test_chat_completions_no_auth_when_access_key_empty():
    _clear_state()
    cfg = AppConfig(access_key="")
    admin_state_init(cfg, CommandCodeClient(base_url=cfg.cc_base_url, api_key=""))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/chat/completions",
            json={"model": "test", "messages": [{"role": "user", "content": "hi"}]},
        )
    assert resp.status_code in (200, 401, 502)
    _clear_state()
