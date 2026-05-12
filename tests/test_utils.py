import pytest
from cc_adapter.core.utils import normalize_api_keys, is_deepseek_v4_model


class TestNormalizeApiKeys:
    def test_empty_string_returns_empty(self):
        assert normalize_api_keys("") == []

    def test_single_key_string_returns_list(self):
        assert normalize_api_keys("key1") == ["key1"]

    def test_json_array_string(self):
        assert normalize_api_keys('["k1","k2"]') == ["k1", "k2"]

    def test_list_input(self):
        assert normalize_api_keys(["k1", "k2"]) == ["k1", "k2"]

    def test_list_filters_empty(self):
        assert normalize_api_keys(["k1", "", "k2"]) == ["k1", "k2"]

    def test_none_returns_empty(self):
        assert normalize_api_keys(None) == []

    def test_invalid_json_falls_back_to_single(self):
        assert normalize_api_keys("{bad") == ["{bad"]


class TestIsDeepseekV4Model:
    def test_bare_name(self):
        assert is_deepseek_v4_model("deepseek-v4-flash") is True

    def test_qualified_name(self):
        assert is_deepseek_v4_model("deepseek/deepseek-v4-flash") is True

    def test_other_model(self):
        assert is_deepseek_v4_model("claude-sonnet-4-6") is False
