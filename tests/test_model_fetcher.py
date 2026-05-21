from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from cc_adapter.core.model_fetcher import ModelFetcher


class TestModelFetcher:
    def test_fallback_to_hardcoded(self, tmp_path: Path) -> None:
        cache = tmp_path / "models_cache.json"
        mf = ModelFetcher(cache_path=str(cache))
        models = mf.get_models_data()
        assert len(models) >= 19
        ids = {m["id"] for m in models}
        assert "deepseek/deepseek-v4-flash" in ids
        assert "stepfun/Step-3.5-Flash" in ids

    def test_load_cache(self, tmp_path: Path) -> None:
        cache = tmp_path / "models_cache.json"
        cache.write_text(
            json.dumps(
                {
                    "version": "0.99.0",
                    "fetched_at": time.time(),
                    "models": [
                        {
                            "id": "test-org/test-model",
                            "context_window": 500000,
                            "reasoning_efforts": ["low", "high"],
                        }
                    ],
                }
            )
        )
        mf = ModelFetcher(cache_path=str(cache))
        assert mf.get_status()["cached_version"] == "0.99.0"
        assert mf.get_status()["model_count"] == 1
        assert "test-org/test-model" in mf.get_reasoning_efforts()

    def test_build_maps(self, tmp_path: Path) -> None:
        cache = tmp_path / "models_cache.json"
        mf = ModelFetcher(cache_path=str(cache))
        entries = [
            {"id": "org/A", "context_window": 100000, "reasoning_efforts": ["high"]},
            {"id": "no-slash-model", "context_window": 50000, "reasoning_efforts": None},
        ]
        mf._build_maps(entries)

        models = mf.get_models_data()
        assert len(models) == 2
        assert models[0]["id"] == "org/A"
        assert models[0]["owned_by"] == "org"
        assert models[0]["context_length"] == 100000

        assert "A" in mf.get_provider_map()
        assert mf.get_provider_map()["A"] == "org/A"

        assert "org/A" in mf.get_reasoning_efforts()
        assert "no-slash-model" not in mf.get_reasoning_efforts()

    def test_build_maps_no_slash(self, tmp_path: Path) -> None:
        cache = tmp_path / "models_cache.json"
        mf = ModelFetcher(cache_path=str(cache))
        entries = [
            {"id": "gpt-5.5", "context_window": 400000, "reasoning_efforts": ["low", "high"]},
        ]
        mf._build_maps(entries)
        assert mf.get_provider_map()["gpt-5.5"] == "gpt-5.5"
        assert mf.get_models_data()[0]["owned_by"] == "unknown"

    def test_atomic_write_cache(self, tmp_path: Path) -> None:
        cache = tmp_path / "models_cache.json"
        mf = ModelFetcher(cache_path=str(cache))
        data = {"version": "0.99.0", "fetched_at": time.time(), "models": []}
        mf._atomic_write_cache(data)
        assert cache.exists()
        loaded = json.loads(cache.read_text())
        assert loaded["version"] == "0.99.0"

    def test_is_stale_initially(self, tmp_path: Path) -> None:
        mf = ModelFetcher(cache_path=str(tmp_path / "nonexistent.json"))
        assert mf._is_stale()

    def test_not_stale_after_fetch(self, tmp_path: Path) -> None:
        mf = ModelFetcher(cache_path=str(tmp_path / "nonexistent.json"))
        mf._fetched_at = time.time()
        assert not mf._is_stale()

    def test_get_status(self, tmp_path: Path) -> None:
        mf = ModelFetcher(cache_path=str(tmp_path / "models_cache.json"))
        status = mf.get_status()
        assert "cached_version" in status
        assert "fetched_at" in status
        assert "model_count" in status
        assert "last_error" in status
