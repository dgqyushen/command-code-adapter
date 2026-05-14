import asyncio

import httpx
import pytest

from cc_adapter.core.runtime import get_version_checker, reset_version_checker
from cc_adapter.core.version_checker import VersionChecker


class TestRuntimeVersionChecker:
    def test_get_version_checker_returns_singleton(self):
        reset_version_checker()
        c1 = get_version_checker()
        c2 = get_version_checker()
        assert c1 is c2


class TestVersionChecker:
    @pytest.mark.asyncio
    async def test_get_version_returns_default_on_first_call(self):
        checker = VersionChecker()
        version = checker.get_version()
        assert version == "0.25.2"

    @pytest.mark.asyncio
    async def test_get_version_returns_cached_value_without_fetch(self):
        checker = VersionChecker()
        v1 = checker.get_version()
        checker._cached_version = "0.99.0"
        v2 = checker.get_version()
        assert v2 == "0.99.0"

    @pytest.mark.asyncio
    async def test_refresh_updates_version(self, respx_mock):
        respx_mock.get("https://registry.npmjs.org/command-code/latest").mock(
            return_value=httpx.Response(200, json={"version": "0.26.3"})
        )
        checker = VersionChecker()
        await checker.refresh()
        assert checker.get_version() == "0.26.3"
        assert checker.last_fetch_time is not None

    @pytest.mark.asyncio
    async def test_refresh_preserves_old_on_network_failure(self, respx_mock):
        respx_mock.get("https://registry.npmjs.org/command-code/latest").mock(
            side_effect=httpx.RequestError("connection failed")
        )
        checker = VersionChecker()
        checker._cached_version = "0.25.2"
        await checker.refresh()
        assert checker.get_version() == "0.25.2"
        assert checker.last_error is not None
        assert checker.last_fetch_time is not None  # backoff enforced

    @pytest.mark.asyncio
    async def test_refresh_preserves_old_on_bad_json(self, respx_mock):
        respx_mock.get("https://registry.npmjs.org/command-code/latest").mock(
            return_value=httpx.Response(200, text="not json")
        )
        checker = VersionChecker()
        await checker.refresh()
        assert checker.get_version() == "0.25.2"

    @pytest.mark.asyncio
    async def test_refresh_sets_fetch_time_even_when_version_missing(self, respx_mock):
        respx_mock.get("https://registry.npmjs.org/command-code/latest").mock(
            return_value=httpx.Response(200, json={"other": "data"})
        )
        checker = VersionChecker()
        await checker.refresh()
        assert checker.last_fetch_time is not None
        assert checker.get_version() == "0.25.2"

    @pytest.mark.asyncio
    async def test_failure_clears_old_error_before_attempt(self, respx_mock):
        """last_error should be cleared at start of fetch, not just set on failure."""
        checker = VersionChecker()
        checker._last_error = "stale error"
        respx_mock.get("https://registry.npmjs.org/command-code/latest").mock(
            return_value=httpx.Response(200, json={"version": "0.27.0"})
        )
        assert checker.last_error == "stale error"
        await checker.refresh()
        assert checker.get_version() == "0.27.0"
        assert checker.last_error is None  # success clears it

    @pytest.mark.asyncio
    async def test_failure_sets_fetch_time_for_error_backoff(self, respx_mock):
        """After failure, _last_fetch_time is set so _is_stale uses ERROR_BACKOFF."""
        respx_mock.get("https://registry.npmjs.org/command-code/latest").mock(
            side_effect=httpx.RequestError("down")
        )
        checker = VersionChecker()
        await checker.refresh()
        assert checker.last_fetch_time is not None
        assert checker.last_error is not None

    @pytest.mark.asyncio
    async def test_background_fetch_updates_version(self, respx_mock):
        async def delayed(request):
            await asyncio.sleep(0.1)
            return httpx.Response(200, json={"version": "0.28.0"})

        respx_mock.get("https://registry.npmjs.org/command-code/latest").mock(
            side_effect=delayed
        )
        checker = VersionChecker()
        checker._last_fetch_time = 0.0  # stale
        checker.get_version()  # triggers background fetch
        assert checker.get_version() == "0.25.2"  # default while fetching
        await asyncio.sleep(0.2)
        assert checker.get_version() == "0.28.0"  # updated after fetch

    @pytest.mark.asyncio
    async def test_get_version_does_not_trigger_duplicate_fetches(self, respx_mock):
        async def delayed_response(request):
            await asyncio.sleep(0.2)
            return httpx.Response(200, json={"version": "0.26.3"})

        route = respx_mock.get("https://registry.npmjs.org/command-code/latest").mock(
            side_effect=delayed_response
        )
        checker = VersionChecker()
        checker._last_fetch_time = 0.0  # stale

        checker.get_version()
        checker.get_version()  # while first fetch still running

        await asyncio.sleep(0.3)
        assert route.call_count == 1
