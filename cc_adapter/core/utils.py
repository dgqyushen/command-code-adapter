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
