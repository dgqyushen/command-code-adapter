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
