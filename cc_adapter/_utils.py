from __future__ import annotations

import json
from typing import Any


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


def is_deepseek_v4_model(model: str) -> bool:
    bare = model.split("/")[-1]
    return bare.startswith("deepseek-v4")
