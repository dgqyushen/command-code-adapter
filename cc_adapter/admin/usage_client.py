from __future__ import annotations

import asyncio
import structlog

import httpx

from cc_adapter.command_code.headers import make_cc_headers

logger = structlog.get_logger(__name__)

CC_BASE_PATH = "/alpha"

PLAN_NAMES = {
    "individual-go": "Go",
    "individual-pro": "Pro",
    "individual-max": "Max",
    "individual-ultra": "Ultra",
    "teams-pro": "Teams Pro",
}


async def query_token_usage(base_url: str, api_key: str, timeout: float = 15.0) -> dict:
    headers = make_cc_headers(api_key)

    result: dict = {"token": api_key, "label": "", "ok": False, "error": None}

    async with httpx.AsyncClient(timeout=timeout, base_url=base_url) as client:
        try:
            whoami_task = client.get(f"{CC_BASE_PATH}/whoami", headers=headers)
            usage_task = client.get(
                f"{CC_BASE_PATH}/usage/summary",
                headers=headers,
                params={"since": "1970-01-01T00:00:00Z"},
            )
            who_resp, usage_resp = await asyncio.gather(whoami_task, usage_task, return_exceptions=True)

            if isinstance(who_resp, Exception):
                result["error"] = f"Network error: {who_resp}"
                return result

            if who_resp.status_code == 401:
                result["error"] = "Invalid API key"
                return result
            who_resp.raise_for_status()
            who_data = who_resp.json()
            result["user"] = {
                "name": who_data.get("name", ""),
                "email": who_data.get("email", ""),
            }
            org_id = (who_data.get("org") or {}).get("id")

            params: dict[str, str] = {}
            if org_id:
                params["orgId"] = org_id

            async def get_json(path: str, p: dict | None = None) -> dict | None:
                try:
                    r = await client.get(path, headers=headers, params=p or params)
                    r.raise_for_status()
                    return r.json()
                except Exception as e:
                    logger.warning("Usage query failed for %s: %s", path, e)
                    return None

            credits_data, sub_data = await asyncio.gather(
                get_json(f"{CC_BASE_PATH}/billing/credits"),
                get_json(f"{CC_BASE_PATH}/billing/subscriptions"),
            )

            if credits_data and "credits" in credits_data:
                c = credits_data["credits"]
                result["credits"] = {
                    "monthly": c.get("monthlyCredits", 0),
                    "purchased": c.get("purchasedCredits", 0),
                    "free": c.get("freeCredits", 0),
                    "total": c.get("monthlyCredits", 0) + c.get("purchasedCredits", 0) + c.get("freeCredits", 0),
                }

            if sub_data and sub_data.get("success") and sub_data.get("data"):
                s = sub_data["data"]
                plan_id = s.get("planId", "")
                result["subscription"] = {
                    "plan_id": plan_id,
                    "plan_name": PLAN_NAMES.get(plan_id, plan_id),
                    "status": s.get("status", ""),
                    "period_start": s.get("currentPeriodStart", ""),
                    "period_end": s.get("currentPeriodEnd", ""),
                }

            if not isinstance(usage_resp, Exception) and usage_resp is not None and usage_resp.status_code < 400:
                usage_data = usage_resp.json()
                result["usage"] = {
                    "total_cost": usage_data.get("totalCost", 0),
                    "total_count": usage_data.get("totalCount", 0),
                    "models": [
                        {
                            "model_id": m.get("model", ""),
                            "total_cost": m.get("totalCost", 0),
                            "total_count": m.get("count", 0),
                        }
                        for m in usage_data.get("models", [])
                    ],
                }

            result["ok"] = True
            return result

        except httpx.RequestError as e:
            result["error"] = f"Network error: {e}"
            return result


async def query_all_tokens(base_url: str, api_keys: list[str]) -> list[dict]:
    tasks = [query_token_usage(base_url, key) for key in api_keys]
    return list(await asyncio.gather(*tasks))


from datetime import date as date_type, timedelta
from typing import Any


def _fmt_since(d: date_type) -> str:
    return f"{d.isoformat()}T00:00:00Z"


async def _query_usage_since(client: httpx.AsyncClient, headers: dict[str, str], since: str) -> dict[str, Any] | None:
    params: dict[str, str] = {"since": since}
    try:
        r = await client.get(f"{CC_BASE_PATH}/usage/summary", headers=headers, params=params)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.warning("Daily usage query failed for %s: %s", since, e)
        return None


def _sub_models(a: list[dict], b: list[dict]) -> list[dict]:
    b_map = {m["model_id"]: m for m in b}
    result = []
    for ma in a:
        mid = ma["model_id"]
        mb = b_map.get(mid, {"cost": 0, "count": 0})
        cost = round(max(0, ma["cost"] - mb["cost"]), 4)
        if cost < 0.005:
            continue
        result.append(
            {
                "model_id": mid,
                "cost": cost,
                "count": max(0, ma["count"] - mb["count"]),
            }
        )
    return result


async def query_daily_usage(
    base_url: str, api_key: str, start_date: date_type, end_date: date_type, timeout: float = 30.0
) -> list[dict[str, Any]]:
    headers = make_cc_headers(api_key)
    boundaries: list[date_type] = []
    current = start_date
    while current <= end_date:
        boundaries.append(current)
        current += timedelta(days=1)
    boundaries.append(current)

    async with httpx.AsyncClient(timeout=timeout, base_url=base_url) as client:
        snapshots = await asyncio.gather(*(_query_usage_since(client, headers, _fmt_since(b)) for b in boundaries))

    daily_results: list[dict[str, Any]] = []
    for i in range(len(boundaries) - 1):
        cur = snapshots[i]
        nxt = snapshots[i + 1]
        if cur is None or nxt is None:
            continue

        day_cost = round(max(0, cur.get("totalCost", 0) - nxt.get("totalCost", 0)), 4)
        day_count = max(0, cur.get("totalCount", 0) - nxt.get("totalCount", 0))

        cur_models = [
            {"model_id": m.get("model", ""), "cost": m.get("totalCost", 0), "count": m.get("count", 0)}
            for m in cur.get("models", [])
        ]
        nxt_models = [
            {"model_id": m.get("model", ""), "cost": m.get("totalCost", 0), "count": m.get("count", 0)}
            for m in nxt.get("models", [])
        ]

        daily_results.append(
            {
                "date": boundaries[i].isoformat(),
                "total_cost": day_cost,
                "total_count": day_count,
                "models": _sub_models(cur_models, nxt_models),
            }
        )

    return daily_results
