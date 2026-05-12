import pytest


@pytest.fixture(autouse=True)
def isolate_auth_env(monkeypatch):
    monkeypatch.setenv("CC_ADAPTER_ACCESS_KEY", "")
    monkeypatch.setenv("CC_ADAPTER_ADMIN_PASSWORD", "")
