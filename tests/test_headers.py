from cc_adapter.command_code.headers import make_cc_headers, _make_traceparent
from cc_adapter.core.config import AppConfig
from cc_adapter.core.runtime import get_version_checker, reset_version_checker


class TestMakeCcHeaders:
    def test_base_headers(self):
        headers = make_cc_headers()
        assert headers["Content-Type"] == "application/json"
        assert headers["x-command-code-version"] == "0.25.2"
        assert headers["x-cli-environment"] == "production"
        assert headers["x-co-flag"] == "false"
        assert headers["x-taste-learning"] == "false"
        assert "x-project-slug" not in headers
        assert "Authorization" not in headers

    def test_with_api_key(self):
        headers = make_cc_headers("sk-test")
        assert headers["Authorization"] == "Bearer sk-test"

    def test_traceparent_format(self):
        headers = make_cc_headers()
        tp = headers["traceparent"]
        parts = tp.split("-")
        assert len(parts) == 4
        assert parts[0] == "00"
        assert len(parts[1]) == 32
        assert len(parts[2]) == 16
        assert parts[3] == "01"

    def test_traceparent_unique(self):
        tp1 = make_cc_headers()["traceparent"]
        tp2 = make_cc_headers()["traceparent"]
        assert tp1 != tp2

    def test_oss_provider_not_included_when_empty(self, monkeypatch):
        import cc_adapter.core.runtime as runtime

        cfg = AppConfig(oss_primary_provider="")
        monkeypatch.setattr(runtime, "_config", cfg)
        headers = make_cc_headers()
        assert "x-oss-primary-provider" not in headers

    def test_oss_provider_included_when_set(self, monkeypatch):
        import cc_adapter.core.runtime as runtime

        cfg = AppConfig(oss_primary_provider="deepseek")
        monkeypatch.setattr(runtime, "_config", cfg)
        headers = make_cc_headers()
        assert headers["x-oss-primary-provider"] == "deepseek"


class TestVersionHeader:
    def test_x_command_code_version_is_dynamic(self, monkeypatch):
        reset_version_checker()
        headers = make_cc_headers()
        assert "x-command-code-version" in headers
        assert headers["x-command-code-version"] == "0.25.2"  # default before fetch

    def test_x_command_code_version_reflects_checker(self, monkeypatch):
        checker = get_version_checker()
        monkeypatch.setattr(checker, "get_version", lambda: "9.99.9")
        headers = make_cc_headers()
        assert headers["x-command-code-version"] == "9.99.9"
