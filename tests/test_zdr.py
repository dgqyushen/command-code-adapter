import pytest

from cc_adapter.command_code.headers import make_cc_headers
from cc_adapter.core.config import AppConfig


class TestZdrHeaders:
    def test_zdr_header_present_when_config_is_none(self, monkeypatch):
        import cc_adapter.core.runtime as runtime

        monkeypatch.setattr(runtime, "_config", None)

        headers = make_cc_headers(api_key="test-key")
        assert headers["x-cmd-zdr"] == "1"

    def test_zdr_header_present_when_zdr_true(self, monkeypatch):
        import cc_adapter.core.runtime as runtime

        cfg = AppConfig(zdr=True)
        monkeypatch.setattr(runtime, "_config", cfg)

        headers = make_cc_headers(api_key="test-key")
        assert headers["x-cmd-zdr"] == "1"

    def test_zdr_header_absent_when_zdr_false(self, monkeypatch):
        import cc_adapter.core.runtime as runtime

        cfg = AppConfig(zdr=False)
        monkeypatch.setattr(runtime, "_config", cfg)

        headers = make_cc_headers(api_key="test-key")
        assert "x-cmd-zdr" not in headers

    def test_zdr_default_appconfig_has_zdr_true(self):
        cfg = AppConfig()
        assert cfg.zdr is True
