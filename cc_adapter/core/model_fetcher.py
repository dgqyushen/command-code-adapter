from __future__ import annotations

import asyncio
import io
import json
import os
import re
import tarfile
import tempfile
import time
from pathlib import Path

import httpx
import structlog

logger = structlog.get_logger(__name__)

MODEL_PREFIXES = (
    "claude-",
    "gpt-",
    "deepseek/",
    "google/",
    "MiniMaxAI/",
    "moonshotai/",
    "stepfun/",
    "zai-org/",
    "Qwen/",
    "baseten:",
    "anthropic:",
    "openai:",
    "xiaomi/",
)

from cc_adapter.core.constants import NPM_URL, NPM_CACHE_TTL, NPM_ERROR_BACKOFF

DEFAULT_CACHE_FILE = "models_cache.json"


class ModelFetcher:
    def __init__(self, cache_path: str | Path | None = None) -> None:
        self._cache_path = Path(cache_path) if cache_path else Path(DEFAULT_CACHE_FILE)
        self._models_data: list[dict] = []
        self._provider_map: dict[str, str] = {}
        self._reasoning_efforts: dict[str, list[str]] = {}
        self._cached_version: str | None = None
        self._fetched_at: float | None = None
        self._last_error: str | None = None
        self._fetch_task: asyncio.Task[None] | None = None

        from cc_adapter.catalog.models_data import MODELS_DATA
        from cc_adapter.providers.shared.model_mapping import MODEL_PROVIDER_MAP, MODEL_REASONING_EFFORTS_MAP

        self._models_data = list(MODELS_DATA)
        self._provider_map = dict(MODEL_PROVIDER_MAP)
        self._reasoning_efforts = dict(MODEL_REASONING_EFFORTS_MAP)
        self._static_provider_map = dict(MODEL_PROVIDER_MAP)

        self._load_cache()

    def get_models_data(self) -> list[dict]:
        return self._models_data

    def get_provider_map(self) -> dict[str, str]:
        return self._provider_map

    def get_reasoning_efforts(self) -> dict[str, list[str]]:
        return self._reasoning_efforts

    def get_status(self) -> dict:
        return {
            "cached_version": self._cached_version,
            "fetched_at": self._fetched_at,
            "model_count": len(self._models_data),
            "last_error": self._last_error,
        }

    def refresh(self) -> None:
        if self._is_stale():
            try:
                loop = asyncio.get_running_loop()
                if not self._fetch_task or self._fetch_task.done():
                    self._fetch_task = loop.create_task(self._fetch_and_update())
            except RuntimeError:
                pass

    def _sync_maps(self) -> None:
        from cc_adapter.providers.shared.model_mapping import refresh_maps

        refresh_maps(provider_map=self._provider_map, reasoning_efforts=self._reasoning_efforts)

    def _is_stale(self) -> bool:
        if self._fetched_at is None:
            return True
        ttl = NPM_ERROR_BACKOFF if self._last_error else NPM_CACHE_TTL
        return time.monotonic() - self._fetched_at > ttl

    def _load_cache(self) -> bool:
        if not self._cache_path.exists():
            return False
        try:
            data = json.loads(self._cache_path.read_text())
            self._cached_version = data.get("version")
            self._fetched_at = data.get("fetched_at")
            entries = data.get("models", [])
            if entries:
                self._build_maps(entries)
            return True
        except Exception as e:
            logger.warning("model_fetcher.cache_read_failed", error=str(e))
            return False

    def _build_maps(self, entries: list[dict]) -> None:
        models: list[dict] = []
        provider_map: dict[str, str] = {}
        reasoning_efforts: dict[str, list[str]] = {}
        now = int(time.monotonic())

        for e in entries:
            model_id = e["id"]
            ctx = e.get("context_window")
            efforts = e.get("reasoning_efforts")

            parts = model_id.split("/")
            owned_by = parts[0] if len(parts) > 1 else "unknown"
            models.append(
                {
                    "id": model_id,
                    "object": "model",
                    "created": now,
                    "owned_by": owned_by,
                    "context_length": ctx if ctx else 200000,
                }
            )

            short = parts[1] if len(parts) > 1 else model_id
            provider_map[short] = model_id

            if efforts:
                reasoning_efforts[model_id] = list(efforts)

        for k, v in self._static_provider_map.items():
            provider_map.setdefault(k, v)

        self._models_data = models
        self._provider_map = provider_map
        self._reasoning_efforts = reasoning_efforts

    async def _fetch_and_update(self, force: bool = False) -> None:
        self._last_error = None
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(NPM_URL)
                resp.raise_for_status()
                npm_data = resp.json()
                latest_version = npm_data.get("version", "")

            if not latest_version:
                raise ValueError("could not determine latest version")

            if not force and self._cached_version == latest_version and self._fetched_at is not None:
                self._fetched_at = time.monotonic()
                self._sync_maps()
                logger.info("model_fetcher.version_unchanged", version=latest_version)
                return

            tarball_url = npm_data.get("dist", {}).get("tarball", "")
            if not tarball_url:
                raise ValueError("no tarball URL in npm response")

            async with httpx.AsyncClient(timeout=15.0) as client:
                tarball_resp = await client.get(tarball_url)
                tarball_resp.raise_for_status()

            entries = self._extract_models(tarball_resp.content)

            if not entries:
                raise ValueError("no model entries extracted from tarball")

            cache = {
                "version": latest_version,
                "fetched_at": time.monotonic(),
                "models": entries,
            }
            self._atomic_write_cache(cache)

            self._build_maps(entries)
            self._cached_version = latest_version
            self._fetched_at = time.monotonic()
            self._sync_maps()
            logger.info("model_fetcher.updated", version=latest_version, count=len(entries), forced=force)

        except Exception as e:
            self._last_error = str(e)
            self._fetched_at = time.monotonic()
            logger.warning("model_fetcher.fetch_failed", error=str(e))

    async def force_refresh(self) -> None:
        if self._fetch_task and not self._fetch_task.done():
            self._fetch_task.cancel()
            try:
                await self._fetch_task
            except asyncio.CancelledError:
                pass
        await self._fetch_and_update(force=True)

    def _extract_models(self, tarball_data: bytes) -> list[dict]:
        with tarfile.open(fileobj=io.BytesIO(tarball_data), mode="r:gz") as tar:
            mjs = None
            for member in tar.getmembers():
                if member.name.endswith("dist/index.mjs"):
                    f = tar.extractfile(member)
                    if f:
                        mjs = f.read().decode("utf-8")
                    break

            if not mjs:
                raise ValueError("index.mjs not found in tarball")

            entries: list[dict] = []
            for m in re.finditer(r'(\w+)\s*:\s*\{\s*id\s*:\s*["\x60]([^"\x60]+)["\x60]', mjs):
                model_id = m.group(2)
                if not (model_id.startswith(MODEL_PREFIXES) or "/" in model_id):
                    continue

                obj_start = m.start()
                obj_text = mjs[obj_start : obj_start + 2500]

                ctx_match = re.search(r"contextWindow\s*:\s*([^,\s}]+)", obj_text)
                ctx_raw = ctx_match.group(1).strip() if ctx_match else None
                context_window = int(float(ctx_raw)) if ctx_raw else None

                re_match = re.search(r"reasoningEfforts\s*:\s*(\[[^\]]+\])", obj_text)
                efforts = json.loads(re_match.group(1)) if re_match else None

                entries.append(
                    {
                        "id": model_id,
                        "context_window": context_window,
                        "reasoning_efforts": efforts,
                    }
                )

            entries.sort(key=lambda x: -(x.get("context_window") or 0))
            return entries

    def _atomic_write_cache(self, data: dict) -> None:
        fd, tmp_path = tempfile.mkstemp(suffix=".json", prefix="models_cache_")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp_path, str(self._cache_path))
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
