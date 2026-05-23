import json
from datetime import date, timedelta

import httpx
import pytest
import respx

from cc_adapter.admin.usage_client import (
    query_token_usage,
    query_all_tokens,
    query_daily_usage,
)


@pytest.fixture
def base_url():
    return "https://api.commandcode.ai"


@pytest.fixture
def api_key():
    return "test-api-key"


class TestQueryTokenUsage:
    @pytest.mark.asyncio
    async def test_success_with_all_data(self, base_url, api_key):
        with respx.mock(base_url=base_url) as mock:
            mock.get("/alpha/whoami").mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "name": "Test User",
                        "email": "test@example.com",
                        "org": {"id": "org_123"},
                    },
                )
            )
            mock.get("/alpha/usage/summary", params={"since": "1970-01-01T00:00:00Z"}).mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "totalCost": 12.50,
                        "totalCount": 500,
                        "models": [
                            {"model": "deepseek-v4", "totalCost": 10.0, "count": 400},
                            {"model": "step-3.5", "totalCost": 2.5, "count": 100},
                        ],
                    },
                )
            )
            mock.get("/alpha/billing/credits", params={"orgId": "org_123"}).mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "credits": {
                            "monthlyCredits": 1000,
                            "purchasedCredits": 500,
                            "freeCredits": 50,
                        }
                    },
                )
            )
            mock.get("/alpha/billing/subscriptions", params={"orgId": "org_123"}).mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "success": True,
                        "data": {
                            "planId": "individual-pro",
                            "status": "active",
                            "currentPeriodStart": "2025-01-01T00:00:00Z",
                            "currentPeriodEnd": "2025-02-01T00:00:00Z",
                        },
                    },
                )
            )

            result = await query_token_usage(base_url, api_key)

        assert result["ok"] is True
        assert result["user"]["email"] == "test@example.com"
        assert result["user"]["name"] == "Test User"
        assert result["usage"]["total_cost"] == 12.50
        assert result["usage"]["total_count"] == 500
        assert len(result["usage"]["models"]) == 2
        assert result["credits"]["monthly"] == 1000
        assert result["credits"]["purchased"] == 500
        assert result["credits"]["free"] == 50
        assert result["credits"]["total"] == 1550
        assert result["subscription"]["plan_id"] == "individual-pro"
        assert result["subscription"]["plan_name"] == "Pro"
        assert result["subscription"]["status"] == "active"

    @pytest.mark.asyncio
    async def test_unauthorized_key(self, base_url, api_key):
        with respx.mock(base_url=base_url) as mock:
            mock.get("/alpha/whoami").mock(return_value=httpx.Response(401, json={"error": "unauthorized"}))

            result = await query_token_usage(base_url, api_key)

        assert result["ok"] is False
        assert result["error"] == "Invalid API key"

    @pytest.mark.asyncio
    async def test_whoami_network_error(self, base_url, api_key):
        with respx.mock(base_url=base_url) as mock:
            mock.get("/alpha/whoami").mock(side_effect=httpx.ConnectError("connection refused"))

            result = await query_token_usage(base_url, api_key)

        assert result["ok"] is False
        assert "Network error" in result["error"]
        assert "connection refused" in result["error"]

    @pytest.mark.asyncio
    async def test_ok_without_org(self, base_url, api_key):
        with respx.mock(base_url=base_url) as mock:
            mock.get("/alpha/whoami").mock(return_value=httpx.Response(200, json={"name": "User", "email": "u@e.com"}))
            mock.get("/alpha/usage/summary", params={"since": "1970-01-01T00:00:00Z"}).mock(
                return_value=httpx.Response(200, json={"totalCost": 0, "totalCount": 0})
            )
            mock.get("/alpha/billing/credits").mock(return_value=httpx.Response(200, json={"credits": {}}))
            mock.get("/alpha/billing/subscriptions").mock(
                return_value=httpx.Response(
                    200,
                    json={"success": False, "data": None},
                )
            )

            result = await query_token_usage(base_url, api_key)

        assert result["ok"] is True
        assert "subscription" not in result

    @pytest.mark.asyncio
    async def test_credits_and_subs_fail_gracefully(self, base_url, api_key):
        with respx.mock(base_url=base_url) as mock:
            mock.get("/alpha/whoami").mock(
                return_value=httpx.Response(
                    200,
                    json={"name": "U", "email": "u@e.com", "org": {"id": "o1"}},
                )
            )
            mock.get("/alpha/usage/summary", params={"since": "1970-01-01T00:00:00Z"}).mock(
                return_value=httpx.Response(200, json={"totalCost": 0, "totalCount": 0})
            )
            mock.get("/alpha/billing/credits", params={"orgId": "o1"}).mock(return_value=httpx.Response(500))
            mock.get("/alpha/billing/subscriptions", params={"orgId": "o1"}).mock(
                side_effect=httpx.ConnectError("down")
            )

            result = await query_token_usage(base_url, api_key)

        assert result["ok"] is True
        assert "credits" not in result
        assert "subscription" not in result

    @pytest.mark.asyncio
    async def test_usage_response_error(self, base_url, api_key):
        with respx.mock(base_url=base_url) as mock:
            mock.get("/alpha/whoami").mock(return_value=httpx.Response(200, json={"name": "U", "email": "u@e.com"}))
            mock.get("/alpha/usage/summary", params={"since": "1970-01-01T00:00:00Z"}).mock(
                return_value=httpx.Response(500)
            )
            mock.get("/alpha/billing/credits").mock(return_value=httpx.Response(200, json={}))
            mock.get("/alpha/billing/subscriptions").mock(return_value=httpx.Response(200, json={}))

            result = await query_token_usage(base_url, api_key)

        assert result["ok"] is True
        assert "usage" not in result


class TestQueryAllTokens:
    @pytest.mark.asyncio
    async def test_multiple_keys(self, base_url):
        with respx.mock(base_url=base_url) as mock:
            mock.get("/alpha/whoami").mock(return_value=httpx.Response(200, json={"name": "User", "email": "a@b.com"}))
            mock.get("/alpha/usage/summary").mock(
                return_value=httpx.Response(200, json={"totalCost": 0, "totalCount": 0})
            )
            mock.get("/alpha/billing/credits").mock(return_value=httpx.Response(200, json={}))
            mock.get("/alpha/billing/subscriptions").mock(return_value=httpx.Response(200, json={}))

            results = await query_all_tokens(base_url, ["key1", "key2", "key3"])

        assert len(results) == 3
        for r in results:
            assert r["ok"] is True


class TestQueryDailyUsage:
    @pytest.mark.asyncio
    async def test_daily_usage_two_days(self, base_url, api_key):
        start = date(2025, 1, 1)
        end = date(2025, 1, 2)

        with respx.mock(base_url=base_url) as mock:
            mock.get("/alpha/usage/summary", params={"since": "2025-01-01T00:00:00Z"}).mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "totalCost": 10.0,
                        "totalCount": 100,
                        "models": [{"model": "m1", "totalCost": 10.0, "count": 100}],
                    },
                )
            )
            mock.get("/alpha/usage/summary", params={"since": "2025-01-02T00:00:00Z"}).mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "totalCost": 18.0,
                        "totalCount": 180,
                        "models": [{"model": "m1", "totalCost": 18.0, "count": 180}],
                    },
                )
            )
            mock.get("/alpha/usage/summary", params={"since": "2025-01-03T00:00:00Z"}).mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "totalCost": 18.0,
                        "totalCount": 180,
                        "models": [{"model": "m1", "totalCost": 18.0, "count": 180}],
                    },
                )
            )

            results = await query_daily_usage(base_url, api_key, start, end)

        assert len(results) == 2
        assert results[0]["date"] == "2025-01-01"
        assert results[1]["date"] == "2025-01-02"

    @pytest.mark.asyncio
    async def test_daily_usage_handles_none_snapshots(self, base_url, api_key):
        start = date(2025, 1, 1)
        end = date(2025, 1, 1)

        with respx.mock(base_url=base_url) as mock:
            mock.get("/alpha/usage/summary", params={"since": "2025-01-01T00:00:00Z"}).mock(
                return_value=httpx.Response(500)
            )
            mock.get("/alpha/usage/summary", params={"since": "2025-01-02T00:00:00Z"}).mock(
                return_value=httpx.Response(200, json={"totalCost": 5, "totalCount": 50})
            )

            results = await query_daily_usage(base_url, api_key, start, end)

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_daily_usage_zero_consumption(self, base_url, api_key):
        start = date(2025, 1, 1)
        end = date(2025, 1, 1)

        with respx.mock(base_url=base_url) as mock:
            mock.get("/alpha/usage/summary", params={"since": "2025-01-01T00:00:00Z"}).mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "totalCost": 10,
                        "totalCount": 100,
                        "models": [{"model": "m1", "totalCost": 10, "count": 100}],
                    },
                )
            )
            mock.get("/alpha/usage/summary", params={"since": "2025-01-02T00:00:00Z"}).mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "totalCost": 10,
                        "totalCount": 100,
                        "models": [{"model": "m1", "totalCost": 10, "count": 100}],
                    },
                )
            )

            results = await query_daily_usage(base_url, api_key, start, end)

        assert len(results) == 1
        assert results[0]["total_cost"] == 0
        assert results[0]["total_count"] == 0
