# CC-Adapter — Agent Guide

## Commands

```bash
poetry install              # install deps
poetry run pytest           # run all tests
poetry run black .          # format code
poetry run python -m cc_adapter  # start server (also: cc-adapter)
docker compose up -d        # run via Docker
```

## Config quirk

Code uses `pydantic-settings` with env prefix `CC_ADAPTER_`. The env var for API key is `CC_ADAPTER_CC_API_KEY` (not `CC_API_KEY` as `.env.example` and README suggest). The `.env` file at repo root has the correct names.

All config fields in `cc_adapter/config.py:AppConfig`.

## Architecture

- **FastAPI** app at `cc_adapter/main.py` → single route `POST /v1/chat/completions`
- **Translator** converts OpenAI-format requests → Command Code API format and back
- **Client** (`cc_adapter/client.py`) streams SSE from CC API's `/alpha/generate` endpoint
- **Admin panel** at `/admin` with custom HMAC-signed token auth (not JWT)
- Runtime config changes via admin API update the global module state (`admin/state.py`)

## Translation quirks

- **Model auto-prefixing**: bare model names like `deepseek-v4-flash` get a provider prefix (`deepseek/`). See `MODEL_PROVIDER_MAP` in `translator/request.py`.
- **Unsupported params silently dropped**: `top_p`, `stop`, `n`, `presence_penalty`, `frequency_penalty`, `user`, `response_format` → logged as warning, ignored.
- **Tool param mapping**: OpenCode-style (`filePath`/`oldString`/`newString`) ↔ CC-style (`path`/`old_str`/`new_str`) bidirectional mapping in `translator/tool_mapping.py`.
- **System prompt** extracted from messages, passed as top-level `system` field (not in messages array).
- **`tool` role messages** are rewritten to `user` role with `tool_call_id` preserved.

## Testing

- `pytest`, `pytest-asyncio` (all async tests need `@pytest.mark.asyncio`)
- No linter/typechecker config — only tests verify correctness
- Formatter: `black` (line-length 120, configured in `pyproject.toml`)
- Integration tests use `ASGITransport` (no real HTTP); CC API key not needed for unit tests
