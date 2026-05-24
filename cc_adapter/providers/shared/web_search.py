from __future__ import annotations

import copy
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

WEB_SEARCH_TOOL_DEFINITION = {
    "name": "web_search",
    "description": "Search the web for current information",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The search query"},
        },
        "required": ["query"],
    },
}


def is_web_search_enabled(config: Any) -> bool:
    if not config or not config.web_search_provider:
        return False
    provider = config.web_search_provider.strip().lower()
    if provider == "deepseek":
        return bool(config.deepseek_api_key)
    if provider == "brave":
        return bool(config.brave_api_key)
    if provider == "tavily":
        return bool(config.tavily_api_key)
    return False


def inject_web_search_tool(tools: list[dict]) -> list[dict]:
    if any(t.get("name") == "web_search" for t in tools):
        return tools
    return tools + [copy.deepcopy(WEB_SEARCH_TOOL_DEFINITION)]


async def execute_search(query: str, config) -> list[dict]:
    provider = config.web_search_provider.strip().lower()
    if provider == "deepseek":
        return await _search_deepseek(query, config.deepseek_api_key)
    if provider == "brave":
        return await _search_brave(query, config.brave_api_key)
    if provider == "tavily":
        return await _search_tavily(query, config.tavily_api_key)
    return []


def format_search_results(results: list[dict], max_results: int = 10, max_snippet_length: int = 500) -> str:
    if not results:
        return "No search results found."
    lines = []
    for i, r in enumerate(results[:max_results], 1):
        title = r.get("title") or "Untitled"
        url = r.get("url") or ""
        snippet = r.get("snippet") or ""
        if len(snippet) > max_snippet_length:
            snippet = snippet[: max_snippet_length - 3] + "..."
        lines.append(f"{i}. {title}")
        if url:
            lines.append(f"   URL: {url}")
        if snippet:
            lines.append(f"   {snippet}")
        lines.append("")
    return "\n".join(lines).strip()


async def _search_deepseek(query: str, api_key: str) -> list[dict]:
    url = "https://api.deepseek.com/v1/search"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {"query": query, "max_results": 10}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return [
                {"title": item.get("title", ""), "url": item.get("url", ""), "snippet": item.get("snippet", "")}
                for item in data.get("results", data.get("data", []))
            ]
    except Exception as e:
        logger.warning("web_search.deepseek_failed", error=str(e))
        return [{"title": "Search Error", "url": "", "snippet": f"DeepSeek search failed: {e}"}]


async def _search_brave(query: str, api_key: str) -> list[dict]:
    url = "https://api.search.brave.com/res/v1/web/search"
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": api_key,
    }
    params = {"q": query, "count": 10}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()
            web = data.get("web", {})
            results = web.get("results", [])
            return [
                {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("description", "")}
                for r in results
            ]
    except Exception as e:
        logger.warning("web_search.brave_failed", error=str(e))
        return [{"title": "Search Error", "url": "", "snippet": f"Brave search failed: {e}"}]


async def _search_tavily(query: str, api_key: str) -> list[dict]:
    url = "https://api.tavily.com/search"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {"query": query, "max_results": 10}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return [
                {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("content", "")}
                for r in data.get("results", [])
            ]
    except Exception as e:
        logger.warning("web_search.tavily_failed", error=str(e))
        return [{"title": "Search Error", "url": "", "snippet": f"Tavily search failed: {e}"}]
