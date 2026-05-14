from cc_adapter.command_code.headers import make_cc_headers
from cc_adapter.core.runtime import get_version_checker, reset_version_checker


class TestMakeCcHeaders:
    def test_base_headers(self):
        headers = make_cc_headers()
        assert headers["Content-Type"] == "application/json"
        assert headers["x-command-code-version"] == "0.25.2"
        assert headers["x-cli-environment"] == "production"
        assert headers["x-project-slug"] == "adapter"
        assert headers["x-internal-team-flag"] == "false"
        assert headers["x-taste-learning"] == "false"
        assert "Authorization" not in headers

    def test_with_api_key(self):
        headers = make_cc_headers("sk-test")
        assert headers["Authorization"] == "Bearer sk-test"


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
