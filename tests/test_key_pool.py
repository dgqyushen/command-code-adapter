import time

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from cc_adapter.core.key_pool import KeyPool


class TestKeyPoolSelectKey:
    @pytest.mark.asyncio
    async def test_select_key_returns_first_key_when_no_credits_cached(self):
        pool = KeyPool(keys=["key1", "key2", "key3"], base_url="https://api.example.com")
        key = await pool.select_key()
        assert key == "key1"

    @pytest.mark.asyncio
    async def test_select_key_skips_zero_credit_keys(self):
        pool = KeyPool(keys=["key1", "key2", "key3"], base_url="https://api.example.com")
        pool._credits = {"key1": 0, "key2": 100, "key3": 50}
        key = await pool.select_key()
        assert key == "key2"

    @pytest.mark.asyncio
    async def test_select_key_skips_unavailable_keys(self):
        pool = KeyPool(keys=["key1", "key2", "key3"], base_url="https://api.example.com")
        pool._credits = {"key1": 100, "key2": 200, "key3": 300}
        pool.mark_unavailable("key1")
        key = await pool.select_key()
        assert key == "key2"

    @pytest.mark.asyncio
    async def test_select_key_falls_back_to_first_when_all_exhausted(self):
        pool = KeyPool(keys=["key1", "key2"], base_url="https://api.example.com")
        pool._credits = {"key1": 0, "key2": 0}
        key = await pool.select_key()
        assert key == "key1"

    @pytest.mark.asyncio
    async def test_select_key_returns_none_when_no_keys(self):
        pool = KeyPool(keys=[], base_url="https://api.example.com")
        key = await pool.select_key()
        assert key is None

    @pytest.mark.asyncio
    async def test_select_key_respects_precedence_order(self):
        pool = KeyPool(keys=["keyA", "keyB", "keyC"], base_url="https://api.example.com")
        pool._credits = {"keyA": 0, "keyB": 999, "keyC": 999}
        key = await pool.select_key()
        assert key == "keyB"


class TestKeyPoolMarkUnavailable:
    def test_mark_unavailable_adds_key_to_set(self):
        pool = KeyPool(keys=["k1", "k2"], base_url="https://api.example.com")
        pool.mark_unavailable("k1")
        assert "k1" in pool._unavailable

    def test_clear_unavailable_resets_set(self):
        pool = KeyPool(keys=["k1", "k2"], base_url="https://api.example.com")
        pool.mark_unavailable("k1")
        pool.mark_unavailable("k2")
        pool.clear_unavailable()
        assert len(pool._unavailable) == 0


class TestKeyPoolCreditsCache:
    def test_get_credits_returns_none_when_not_cached(self):
        pool = KeyPool(keys=["k1"], base_url="https://api.example.com")
        assert pool.get_credits("k1") is None

    def test_get_credits_returns_cached_value(self):
        pool = KeyPool(keys=["k1"], base_url="https://api.example.com")
        pool._credits["k1"] = 500
        assert pool.get_credits("k1") == 500


class TestKeyPoolStaleness:
    def test_is_stale_returns_true_when_never_fetched(self):
        pool = KeyPool(keys=["k1"], base_url="https://api.example.com")
        assert pool._is_stale()

    def test_is_stale_returns_false_within_ttl(self):
        pool = KeyPool(keys=["k1"], base_url="https://api.example.com")
        pool._last_fetch = time.monotonic()
        assert not pool._is_stale()

    def test_is_stale_returns_true_after_ttl(self):
        pool = KeyPool(keys=["k1"], base_url="https://api.example.com")
        pool._last_fetch = time.monotonic() - 2000
        assert pool._is_stale()

    def test_is_stale_uses_error_backoff_when_last_error_set(self):
        pool = KeyPool(keys=["k1"], base_url="https://api.example.com")
        pool._last_error = "some error"
        pool._last_fetch = time.monotonic() - 100
        assert pool._is_stale()


class TestKeyPoolRefresh:
    @pytest.mark.asyncio
    async def test_refresh_updates_credits_from_api(self):
        pool = KeyPool(keys=["key1", "key2"], base_url="https://api.example.com")

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "credits": {"monthlyCredits": 100, "purchasedCredits": 50, "freeCredits": 10}
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value.get.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            await pool.refresh()

        assert pool.get_credits("key1") == 160
        assert pool.get_credits("key2") == 160
        assert pool._last_fetch is not None
        assert pool._last_error is None

    @pytest.mark.asyncio
    async def test_refresh_handles_partial_failures(self):
        pool = KeyPool(keys=["key1", "key2"], base_url="https://api.example.com")

        async def mock_fetch(api_key):
            if api_key == "key2":
                raise Exception("network error")
            return 160

        pool._fetch_credits = mock_fetch
        await pool.refresh()

        assert pool.get_credits("key1") == 160
        assert pool.get_credits("key2") is None
        assert pool._last_fetch is not None

    @pytest.mark.asyncio
    async def test_refresh_all_failures_sets_last_error(self):
        pool = KeyPool(keys=["key1", "key2"], base_url="https://api.example.com")

        async def mock_fetch(api_key):
            raise Exception("all down")

        pool._fetch_credits = mock_fetch
        await pool.refresh()

        assert pool._last_error == "All credit fetches failed"
        assert pool._last_fetch is not None


class TestKeyPoolSelectKeyUnavailable:
    @pytest.mark.asyncio
    async def test_select_key_skips_unavailable_when_all_credits_zero(self):
        pool = KeyPool(keys=["key1", "key2"], base_url="https://api.example.com")
        pool._credits = {"key1": 0, "key2": 0}
        pool.mark_unavailable("key1")
        key = await pool.select_key()
        assert key == "key2"

    @pytest.mark.asyncio
    async def test_select_key_returns_any_when_all_unavailable_and_zero(self):
        pool = KeyPool(keys=["key1", "key2"], base_url="https://api.example.com")
        pool._credits = {"key1": 0, "key2": 0}
        pool.mark_unavailable("key1")
        pool.mark_unavailable("key2")
        key = await pool.select_key()
        assert key == "key1"
