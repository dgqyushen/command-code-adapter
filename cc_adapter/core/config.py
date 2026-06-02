from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from cc_adapter.core.utils import normalize_api_keys


DEFAULT_MODEL = "deepseek/deepseek-v4-flash"


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CC_ADAPTER_", env_file=".env", extra="ignore")

    host: str = "0.0.0.0"
    port: int = 8080
    log_level: str = "INFO"
    log_format: str = "console"

    cc_api_key: str | list[str] = []
    cc_base_url: str = "https://api.commandcode.ai"
    admin_password: str = ""
    access_key: str = ""
    default_model: str = DEFAULT_MODEL

    http_max_connections: int = 200
    http_max_keepalive_connections: int = 50
    http2: bool = False

    zdr: bool = True

    oss_primary_provider: str = ""

    web_search_provider: str = ""
    deepseek_api_key: str = ""
    deepseek_anthropic_url: str = "https://api.deepseek.com/anthropic"
    web_search_model: str = ""

    @field_validator("cc_api_key", mode="before")
    @classmethod
    def coerce_api_key(cls, v):
        return normalize_api_keys(v)


def get_config_or_default() -> AppConfig:
    from cc_adapter.core.runtime import get_config

    cfg = get_config()
    return cfg if cfg else AppConfig()
