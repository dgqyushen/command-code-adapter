from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

NPM_URL = "https://registry.npmjs.org/command-code/latest"
DEFAULT_VERSION = "0.25.2"
CACHE_TTL = 1800  # 30 minutes


class VersionChecker:
    def __init__(self) -> None:
        self._cached_version: str = DEFAULT_VERSION
        self._last_fetch_time: float | None = None
        self._last_error: str | None = None
        self._fetch_task: asyncio.Task[Any] | None = None

    def get_version(self) -> str:
        if self._is_stale():
            try:
                loop = asyncio.get_running_loop()
                if not self._fetch_task or self._fetch_task.done():
                    self._fetch_task = loop.create_task(self._fetch_and_update())
            except RuntimeError:
                pass
        return self._cached_version

    async def refresh(self) -> None:
        await self._fetch_and_update()

    @property
    def last_fetch_time(self) -> float | None:
        return self._last_fetch_time

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def _is_stale(self) -> bool:
        if self._last_fetch_time is None:
            return True
        return time.monotonic() - self._last_fetch_time > CACHE_TTL

    async def _fetch_and_update(self) -> None:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(NPM_URL)
                response.raise_for_status()
                data = response.json()
                version = data.get("version", "")
                if version:
                    logger.info("version.updated", old=self._cached_version, new=version)
                    self._cached_version = version
                    self._last_fetch_time = time.monotonic()
                    self._last_error = None
                else:
                    logger.warning("version.missing_field", url=NPM_URL)
        except Exception as e:
            self._last_error = str(e)
            logger.warning("version.fetch_failed", error=str(e), url=NPM_URL)
