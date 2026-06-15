from __future__ import annotations

import asyncio
import datetime
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

DEFAULT_DATA_FILE = "token_usage.json"


class TokenRecorder:
    def __init__(self, data_path: str | Path | None = None) -> None:
        self._path = Path(data_path) if data_path else Path(DEFAULT_DATA_FILE)
        self._lock = asyncio.Lock()
        self._data: dict[str, dict[str, int]] = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self._path.exists():
            logger.info("token_recorder.no_file", path=str(self._path))
            return
        try:
            self._data = json.loads(self._path.read_text())
            logger.info("token_recorder.loaded", path=str(self._path), days=len(self._data))
        except Exception as e:
            logger.warning("token_recorder.load_failed", error=str(e))
            self._data = {}

    def _date_key(self) -> str:
        return datetime.date.today().isoformat()

    async def record(self, input_tokens: int, output_tokens: int) -> None:
        self._ensure_loaded()
        total = input_tokens + output_tokens
        if total <= 0:
            return
        async with self._lock:
            day = self._date_key()
            entry = self._data.get(day)
            if entry is None:
                self._data[day] = {"tokens": total, "requests": 1}
            else:
                entry["tokens"] = entry.get("tokens", 0) + total
                entry["requests"] = entry.get("requests", 0) + 1
            self._atomic_write()

    def _atomic_write(self) -> None:
        fd, tmp_path = tempfile.mkstemp(suffix=".json", prefix="token_usage_")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(self._data, f, indent=2, sort_keys=True)
            os.replace(tmp_path, str(self._path))
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def query(self, days: int = 365) -> dict[str, dict[str, int]]:
        self._ensure_loaded()
        cutoff = (datetime.date.today() - datetime.timedelta(days=days - 1)).isoformat()
        return {k: v for k, v in self._data.items() if k >= cutoff}


_recorder: TokenRecorder | None = None


def get_token_recorder() -> TokenRecorder:
    global _recorder
    if _recorder is None:
        _recorder = TokenRecorder()
    return _recorder


def _reset_recorder() -> None:
    global _recorder
    _recorder = None


async def record_daily_tokens(input_tokens: int, output_tokens: int) -> None:
    await get_token_recorder().record(input_tokens, output_tokens)


def query_daily_tokens(days: int = 365) -> dict[str, dict[str, int]]:
    return get_token_recorder().query(days)
