import pytest
from cc_adapter.core.utils import generate_id, normalize_api_keys


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


class TestGenerateId:
    def test_defaults_to_12_char_hex(self):
        result = generate_id()
        assert len(result) == 12
        assert all(c in "0123456789abcdef" for c in result)

    def test_with_prefix(self):
        result = generate_id("chatcmpl-")
        assert result.startswith("chatcmpl-")
        assert len(result) == 21  # 9 prefix + 12 hex

    def test_custom_length(self):
        result = generate_id("msg_", 16)
        assert result.startswith("msg_")
        assert len(result) == 20  # 4 prefix + 16 hex

    def test_zero_length(self):
        result = generate_id("test", 0)
        assert result == "test"

    def test_no_prefix(self):
        result = generate_id(length=8)
        assert len(result) == 8

    def test_unique_values(self):
        results = {generate_id() for _ in range(100)}
        assert len(results) == 100  # all unique
