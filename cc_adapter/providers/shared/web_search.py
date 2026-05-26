from __future__ import annotations

import copy
from typing import Any

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
    return False


def has_anthropic_web_search_tool(tools: Any) -> bool:
    if not tools:
        return False
    for tool in tools:
        name = getattr(tool, "name", None)
        tool_type = getattr(tool, "type", None)
        if isinstance(tool, dict):
            name = tool.get("name")
            tool_type = tool.get("type")
        if name == "web_search" and isinstance(tool_type, str) and tool_type.startswith("web_search"):
            return True
    return False


def inject_web_search_tool(tools: list[dict]) -> list[dict]:
    if any(t.get("name") == "web_search" for t in tools):
        return tools
    return tools + [copy.deepcopy(WEB_SEARCH_TOOL_DEFINITION)]
