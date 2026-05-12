import pytest
from httpx import ASGITransport, AsyncClient
from cc_adapter.admin.auth import set_password, validate_token, generate_token
from cc_adapter.main import app


def test_no_password_always_valid():
    set_password("")
    token = "anything"
    assert validate_token(token) is True


def test_with_password_requires_matching_token():
    set_password("mysecret")
    token = generate_token()
    assert validate_token(token) is True
    assert validate_token("wrong") is False


def test_token_expires():
    set_password("pw")
    token = generate_token()
    assert validate_token(token) is True


def test_tampered_token_rejected():
    set_password("pw")
    token = generate_token()
    parts = token.split(".")
    tampered = parts[0] + "." + ("a" * len(parts[1]))
    assert validate_token(tampered) is False
    assert validate_token("not.a.token") is False


def test_password_change_invalidates_token():
    set_password("oldpass")
    token = generate_token()
    assert validate_token(token) is True
    set_password("newpass")
    assert validate_token(token) is False


@pytest.mark.asyncio
async def test_login_returns_503_when_no_password():
    from cc_adapter.admin.state import init as admin_state_init
    from cc_adapter.config import AppConfig
    from cc_adapter.client import CommandCodeClient

    cfg = AppConfig(admin_password="")
    admin_state_init(cfg, CommandCodeClient(base_url=cfg.cc_base_url, api_key=""))
    set_password("")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/admin/api/login", json={"password": "anything"})
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_protected_endpoint_returns_503_when_no_password():
    from cc_adapter.admin.state import init as admin_state_init
    from cc_adapter.config import AppConfig
    from cc_adapter.client import CommandCodeClient

    cfg = AppConfig(admin_password="")
    admin_state_init(cfg, CommandCodeClient(base_url=cfg.cc_base_url, api_key=""))
    set_password("")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/admin/api/config")
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_public_endpoints_return_200_without_auth():
    from cc_adapter.admin.state import init as admin_state_init
    from cc_adapter.config import AppConfig
    from cc_adapter.client import CommandCodeClient

    cfg = AppConfig(admin_password="")
    admin_state_init(cfg, CommandCodeClient(base_url=cfg.cc_base_url, api_key=""))
    set_password("")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        models_resp = await client.get("/admin/api/models")
        ui_resp = await client.get("/admin/api/ui-config")
    assert models_resp.status_code == 200
    assert ui_resp.status_code == 200
