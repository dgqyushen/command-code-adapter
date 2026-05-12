from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cc_adapter.core.config import AppConfig
    from cc_adapter.command_code.client import CommandCodeClient
    from cc_adapter.providers.openai.request import RequestTranslator
    from cc_adapter.providers.anthropic.request import AnthropicTranslator

_config: AppConfig | None = None
_cc_client: CommandCodeClient | None = None
_request_translator: RequestTranslator | None = None
_anthropic_translator: AnthropicTranslator | None = None


def get_config() -> AppConfig | None:
    return _config


def get_client() -> CommandCodeClient | None:
    return _cc_client


def get_base_url() -> str:
    if _config is not None:
        return _config.cc_base_url
    return "https://api.commandcode.ai"


def get_api_keys() -> list[str]:
    if _config is not None:
        return _config.cc_api_key
    return []


def init(cfg: AppConfig, client: CommandCodeClient) -> None:
    global _config, _cc_client
    _config = cfg
    _cc_client = client


def get_request_translator() -> RequestTranslator | None:
    global _request_translator
    if _request_translator is None:
        from cc_adapter.providers.openai.request import RequestTranslator

        _request_translator = RequestTranslator()
    return _request_translator


def get_anthropic_translator() -> AnthropicTranslator | None:
    global _anthropic_translator
    if _anthropic_translator is None:
        from cc_adapter.providers.anthropic.request import AnthropicTranslator

        _anthropic_translator = AnthropicTranslator()
    return _anthropic_translator
