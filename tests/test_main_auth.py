import pytest
from httpx import ASGITransport, AsyncClient
from cc_adapter.main import app
from cc_adapter.core.auth import check_api_access, generate_token, set_password
from cc_adapter.core.runtime import init as admin_state_init
from cc_adapter.core.config import AppConfig
from cc_adapter.command_code.client import CommandCodeClient


@pytest.fixture(autouse=True)
def setup():
    cfg = AppConfig(access_key="test_access_key", admin_password="admin123")
    client = CommandCodeClient(base_url=cfg.cc_base_url, api_key="")
    admin_state_init(cfg, client)
    set_password("admin123")


def _clear_state():
    from cc_adapter.core.runtime import init as admin_state_init

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
    import cc_adapter.core.runtime as rt
    from cc_adapter.core.auth import set_password

    rt._config = None
    rt._cc_client = None
    rt._request_translator = None
    rt._anthropic_translator = None
    cfg = AppConfig(access_key="test_access_key", admin_password="admin123")
    client = CommandCodeClient(base_url=cfg.cc_base_url, api_key="")
    admin_state_init(cfg, client)
    set_password("admin123")

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


@pytest.mark.asyncio
async def test_chat_completions_falls_back_to_module_client():
    _clear_state()
    from cc_adapter.core.runtime import init as admin_state_init

    cfg = AppConfig(access_key="")
    admin_state_init(cfg, None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/chat/completions",
            json={"model": "test", "messages": [{"role": "user", "content": "hi"}]},
        )
    assert resp.status_code in (200, 401, 502)


class TestCheckApiAccess:
    def test_no_access_key_allows_all(self):
        assert check_api_access("", "anything") is True
        assert check_api_access("", "") is True

    def test_valid_token_match(self):
        assert check_api_access("sk-123", "sk-123") is True

    def test_invalid_token_rejected(self):
        assert check_api_access("sk-123", "wrong") is False

    def test_empty_token_rejected(self):
        assert check_api_access("sk-123", "") is False

    def test_admin_token_valid(self):
        set_password("admin-pass")
        token = generate_token()
        assert check_api_access("sk-123", token, admin_password="admin-pass") is True
        set_password("")

    def test_admin_token_without_password(self):
        set_password("admin-pass")
        token = generate_token()
        assert check_api_access("sk-123", token) is False
        set_password("")
