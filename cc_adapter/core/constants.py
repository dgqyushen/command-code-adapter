from __future__ import annotations

STREAMING_HEADERS: dict[str, str] = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}

NPM_URL: str = "https://registry.npmjs.org/command-code/latest"
NPM_CACHE_TTL: int = 1800
NPM_ERROR_BACKOFF: int = 60

VERSION: str = "0.5.0"
