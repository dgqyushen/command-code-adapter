from __future__ import annotations

import collections
import threading
from typing import Any

_buffer: collections.deque[dict[str, Any]] = collections.deque(maxlen=1000)
_lock = threading.Lock()

_LEVEL_ORDER: dict[str, int] = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "WARN": 30, "ERROR": 40, "CRITICAL": 50}


def append(entry: dict[str, Any]) -> None:
    with _lock:
        _buffer.append(entry)


def get_entries(*, level: str = "INFO", search: str = "", limit: int = 200) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    min_level = _LEVEL_ORDER.get(level.upper(), 20)
    search_lower = search.lower() if search else ""
    results: list[dict[str, Any]] = []
    with _lock:
        for entry in reversed(_buffer):
            entry_level = str(entry.get("level", "")).upper()
            if _LEVEL_ORDER.get(entry_level, -1) != min_level:
                continue
            if search_lower:
                if not _entry_matches(entry, search_lower):
                    continue
            results.append(entry)
            if len(results) >= limit:
                break
    return results


def _entry_matches(entry: dict[str, Any], search_lower: str) -> bool:
    for v in entry.values():
        if isinstance(v, str) and search_lower in v.lower():
            return True
    return False


def buffer_size() -> int:
    with _lock:
        return len(_buffer)


def clear() -> None:
    with _lock:
        _buffer.clear()
