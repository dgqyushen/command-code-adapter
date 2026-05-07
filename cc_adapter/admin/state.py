from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cc_adapter.config import AppConfig
    from cc_adapter.client import CommandCodeClient

_config: AppConfig | None = None
_cc_client: CommandCodeClient | None = None


def init(cfg, client):
    global _config, _cc_client
    _config = cfg
    _cc_client = client


def get_config() -> AppConfig | None:
    return _config


def get_client() -> CommandCodeClient | None:
    return _cc_client


def get_base_url() -> str:
    return _config.cc_base_url if _config else "https://api.commandcode.ai"


def get_api_keys() -> list[str]:
    keys = _config.cc_api_key if _config else []
    if isinstance(keys, str):
        return [keys] if keys else []
    return keys
