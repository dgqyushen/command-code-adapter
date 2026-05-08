# CC-Adapter — Agent Guide

## Commands

```bash
poetry install                 # install deps
poetry run pytest              # run all tests
poetry run black .             # format (line-length 120)
docker build -t dgqyushen/command-code-proxy:latest .   # build image
docker compose up -d                                    # start container
```

## Config quirk

Code uses `pydantic-settings` with env prefix `CC_ADAPTER_`. The env var for API key is `CC_ADAPTER_CC_API_KEY`, and the env var for the CC API base URL is `CC_ADAPTER_CC_BASE_URL`.

All config fields in `cc_adapter/config.py:AppConfig`. Keys support JSON array format: `CC_ADAPTER_CC_API_KEY=["key1","key2"]`.

## Architecture

- **FastAPI** app at `cc_adapter/main.py` → single route `POST /v1/chat/completions`
- **Translator** converts OpenAI-format requests ↔ Command Code API format
- **Client** (`cc_adapter/client.py`) streams SSE from CC API's `/alpha/generate` endpoint
- **Admin panel** at `/admin` — static SPA in `admin/static/`, HMAC token auth (not JWT)
- Runtime config changes via admin API update global module state (`admin/state.py`)

## Translation quirks

- **Model auto-prefixing**: bare names like `deepseek-v4-flash` get a provider prefix (`deepseek/`). See `MODEL_PROVIDER_MAP` in `translator/request.py`.
- **Unsupported params silently dropped**: `top_p`, `stop`, `n`, `presence_penalty`, `frequency_penalty`, `user`, `response_format` → logged as warning, ignored.
- **Tool param mapping**: OpenCode-style (`filePath`/`oldString`/`newString`) ↔ CC-style (`path`/`old_str`/`new_str`) in `translator/tool_mapping.py`.
- **System prompt** extracted from messages, passed as top-level `system` field.
- **`tool` role messages** are rewritten to `user` role with `tool_call_id` preserved.

## Admin playground

Chatbot interface at Playground tab. Model list served from `GET /admin/api/models` (reads `MODEL_PROVIDER_MAP` in `translator/request.py`). Updating the map auto-syncs to frontend.

## Testing

- `pytest`, `pytest-asyncio` — all async tests need `@pytest.mark.asyncio`
- No linter/typechecker config — only tests verify correctness
- Integration tests use `ASGITransport` (no real HTTP); CC API key not needed for unit tests
- Formatter: `black` (line-length 120)

## Docker verification

After any code change, always run `docker build -t dgqyushen/command-code-proxy:latest . && docker compose up -d` to verify the container builds and starts successfully. This catches missing deps, import errors, and config issues.
