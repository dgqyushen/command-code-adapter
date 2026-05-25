from __future__ import annotations

import json
import os
import structlog
import tempfile
from pathlib import Path
from typing import Any

from cc_adapter.core.config import AppConfig
from cc_adapter.core.utils import normalize_api_keys
from cc_adapter.command_code.client import CommandCodeClient


_CONFIG_CLIENT_FIELDS = {"cc_api_key", "cc_base_url"}

FIELD_MAP = {
    "cc_api_key": "CC_ADAPTER_CC_API_KEY",
    "cc_base_url": "CC_ADAPTER_CC_BASE_URL",
    "host": "CC_ADAPTER_HOST",
    "port": "CC_ADAPTER_PORT",
    "log_level": "CC_ADAPTER_LOG_LEVEL",
    "log_format": "CC_ADAPTER_LOG_FORMAT",
    "default_model": "CC_ADAPTER_DEFAULT_MODEL",
    "zdr": "CC_ADAPTER_ZDR",
}

logger = structlog.get_logger(__name__)


def _apply_config_fields(cfg: AppConfig, updates: dict[str, Any]) -> bool:
    changed_client = False
    for field, value in updates.items():
        if field == "cc_api_key":
            value = normalize_api_keys(value)
        setattr(cfg, field, value)
        if field in _CONFIG_CLIENT_FIELDS:
            changed_client = True
    return changed_client


def _recreate_client(cfg: AppConfig) -> CommandCodeClient | None:
    from cc_adapter.core.runtime import get_client, init as state_init, create_client

    old = get_client()
    state_init(cfg, create_client(cfg))
    return old


class ConfigManager:
    @staticmethod
    def update_env_file(updates: dict[str, Any], env_path: str | Path = ".env") -> None:
        env_path = Path(env_path)
        if not env_path.exists():
            env_path.write_text("")

        lines = env_path.read_text().splitlines(keepends=True)
        existing_keys = set()

        for i, line in enumerate(lines):
            stripped = line.strip()
            if "=" not in stripped or stripped.startswith("#"):
                continue
            key = stripped.split("=", 1)[0].strip()
            for field_name, env_key in FIELD_MAP.items():
                if key == env_key and field_name in updates:
                    value = (
                        normalize_api_keys(updates[field_name]) if field_name == "cc_api_key" else updates[field_name]
                    )
                    if field_name == "cc_api_key":
                        lines[i] = f"{env_key}={json.dumps(value)}\n"
                    else:
                        lines[i] = f"{env_key}={value}\n"
                    existing_keys.add(field_name)

        for field_name, env_key in FIELD_MAP.items():
            if field_name in updates and field_name not in existing_keys:
                value = normalize_api_keys(updates[field_name]) if field_name == "cc_api_key" else updates[field_name]
                if field_name == "cc_api_key":
                    lines.append(f"{env_key}={json.dumps(value)}\n")
                else:
                    lines.append(f"{env_key}={updates[field_name]}\n")

        content = "".join(lines)
        fd, tmp_path = tempfile.mkstemp(suffix=".env", prefix=".env_", text=True)
        try:
            with os.fdopen(fd, "w") as f:
                f.write(content)
            os.replace(tmp_path, str(env_path))
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    @staticmethod
    async def apply_config_update(updates: dict[str, Any]) -> None:
        from cc_adapter.core.runtime import get_config

        cfg = get_config()
        if cfg is None:
            return
        changed_client = _apply_config_fields(cfg, updates)
        if changed_client:
            old = _recreate_client(cfg)
            if old is not None:
                await old.aclose()
        logger.info("admin.config.updated", fields=list(updates.keys()))
