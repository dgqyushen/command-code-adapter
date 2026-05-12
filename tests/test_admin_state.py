import pytest
from cc_adapter.core.runtime import init, get_config, get_client, get_base_url, get_api_keys
from cc_adapter.core.config import AppConfig
from cc_adapter.command_code.client import CommandCodeClient


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def _cfg(**kw):
    return AppConfig(**kw)


class TestAdminState:
    def test_init_and_get(self):
        cfg = _cfg(cc_api_key="test_key")
        client = CommandCodeClient(base_url=cfg.cc_base_url, api_key="test_key")
        init(cfg, client)
        assert get_config() is cfg
        assert get_client() is client

    def test_get_base_url_default(self):
        cfg = _cfg()
        client = CommandCodeClient(base_url=cfg.cc_base_url, api_key="")
        init(cfg, client)
        assert get_base_url() == "https://api.commandcode.ai"

    def test_get_base_url_custom(self):
        cfg = _cfg(cc_base_url="https://custom.test")
        client = CommandCodeClient(base_url=cfg.cc_base_url, api_key="")
        init(cfg, client)
        assert get_base_url() == "https://custom.test"

    def test_get_api_keys(self):
        cfg = _cfg(cc_api_key=["k1", "k2"])
        client = CommandCodeClient(base_url=cfg.cc_base_url, api_key="k1")
        init(cfg, client)
        assert get_api_keys() == ["k1", "k2"]

    def test_get_api_keys_empty_default(self):
        cfg = _cfg()
        client = CommandCodeClient(base_url=cfg.cc_base_url, api_key="")
        init(cfg, client)
        assert get_api_keys() == []
