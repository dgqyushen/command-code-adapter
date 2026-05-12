from __future__ import annotations

import asyncio
import logging

import httpx

from cc_adapter.command_code.headers import make_cc_headers

logger = logging.getLogger(__name__)

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
            who_resp = await client.get(f"{CC_BASE_PATH}/whoami", headers=headers)
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

            params = {}
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

            credits_data, sub_data, usage_data = await asyncio.gather(
                get_json(f"{CC_BASE_PATH}/billing/credits"),
                get_json(f"{CC_BASE_PATH}/billing/subscriptions"),
                get_json(f"{CC_BASE_PATH}/usage/summary", {"since": "1970-01-01T00:00:00Z"}),
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

            if usage_data:
                result["usage"] = {
                    "total_cost": usage_data.get("totalCost", 0),
                    "total_count": usage_data.get("totalCount", 0),
                    "models": [
                        {
                            "model_id": m.get("modelId", ""),
                            "total_cost": m.get("totalCost", 0),
                            "total_count": m.get("totalCount", 0),
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
