from __future__ import annotations

import json
import uuid
from typing import Any


def generate_id(prefix: str = "", length: int = 12) -> str:
    return f"{prefix}{uuid.uuid4().hex[:length]}"


def normalize_api_keys(value: str | list[str] | None) -> list[str]:
    if isinstance(value, list):
        return [k for k in value if k]
    if isinstance(value, str):
        if not value:
            return []
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [k for k in parsed if k]
        except (json.JSONDecodeError, TypeError):
            pass
        return [value]
    return []


def parse_usage(raw_usage: dict | None) -> dict | None:
    if not raw_usage:
        return None
    input_t = raw_usage.get("inputTokens", 0)
    output_t = raw_usage.get("outputTokens", 0)
    result = {
        "input_tokens": input_t,
        "output_tokens": output_t,
        "total_tokens": input_t + output_t,
    }
    reasoning_tokens = raw_usage.get("reasoningTokens")
    if reasoning_tokens:
        result["output_tokens_details"] = {"reasoning_tokens": reasoning_tokens}
    return result


def format_sse(event: str | None, data: dict[str, Any] | str) -> str:
    if isinstance(data, dict):
        json_data = json.dumps(data, ensure_ascii=False, default=str)
    else:
        json_data = data
    if event:
        return f"event: {event}\ndata: {json_data}\n\n"
    return f"data: {json_data}\n\n"


def parse_tool_arguments(raw: Any, label: str = "arguments") -> dict[str, Any]:
    if raw is None or raw == "":
        return {}
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return {}
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {}
    if isinstance(parsed, dict):
        return parsed
    return {}
