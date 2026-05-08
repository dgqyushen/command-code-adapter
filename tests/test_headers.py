from cc_adapter.headers import make_cc_headers, CC_BASE_HEADERS


class TestMakeCcHeaders:
    def test_base_headers(self):
        headers = make_cc_headers()
        for k, v in CC_BASE_HEADERS.items():
            assert headers[k] == v
        assert "Authorization" not in headers

    def test_with_api_key(self):
        headers = make_cc_headers("sk-test")
        assert headers["Authorization"] == "Bearer sk-test"
