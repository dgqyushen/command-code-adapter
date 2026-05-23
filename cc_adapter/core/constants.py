from __future__ import annotations

import tomllib
from pathlib import Path

STREAMING_HEADERS: dict[str, str] = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}

NPM_URL: str = "https://registry.npmjs.org/command-code/latest"
NPM_CACHE_TTL: int = 1800
NPM_ERROR_BACKOFF: int = 60

KEY_CREDITS_CACHE_TTL = 1800
KEY_CREDITS_ERROR_BACKOFF = 60


def _load_version() -> str:
    _pyproject = Path(__file__).parent.parent.parent / "pyproject.toml"
    try:
        with open(_pyproject, "rb") as f:
            return tomllib.load(f)["tool"]["poetry"]["version"]
    except (FileNotFoundError, KeyError):
        return "0.6.0"


VERSION: str = _load_version()
