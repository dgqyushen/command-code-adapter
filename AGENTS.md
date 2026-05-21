# CC-Adapter — Agent Guide

## Commands

```bash
poetry install                    # install deps
poetry run pytest                 # run full test suite
poetry run black .                # format (line-length 120)
poetry run python -m cc_adapter   # dev server (port 8080, or $CC_ADAPTER_PORT)
poetry run cc-adapter             # same, via pyproject.toml scripts
bash run.sh                       # alternative: sources .env, runs uvicorn directly
docker build -t dgqyushen/command-code-proxy:latest .
docker compose up -d              # compose.yml + optional compose.override.yml
```

**Version note**: `pyproject.toml` version (`0.4.4`) often lags behind `main.py:46` + `admin/router.py:277` (`0.4.5`). Bump all three on release.

## Routes

| Path | Handler | Auth |
|---|---|---|
| `POST /v1/chat/completions` | `providers/openai/router.py` | access_key |
| `POST /v1/messages` | `providers/anthropic/router.py` | access_key (or x-api-key) |
| `POST /v1/responses` | `providers/openai/responses_router.py` | access_key |
| `GET /v1/models` | `main.py` (dynamic via `get_models_data()`) | none |
| `GET /admin/api/models` | `admin/router.py` (public listing, no auth) | none |

Entry: `cc_adapter/__main__.py` → `main.py:run()` → uvicorn. Import: `from cc_adapter.main import app`.

## Config (prefix `CC_ADAPTER_`)

Fields in `core/config.py:AppConfig` (loaded eagerly from `.env` at import).

| Env var | Default | Notes |
|---|---|---|
| `CC_ADAPTER_CC_API_KEY` | — | `str \| list[str]` — JSON array: `["k1","k2"]` |
| `CC_ADAPTER_ACCESS_KEY` | — | Bearer token auth (all endpoints) |
| `CC_ADAPTER_CC_BASE_URL` | `https://api.commandcode.ai` | |
| `CC_ADAPTER_DEFAULT_MODEL` | `deepseek/deepseek-v4-flash` | |
| `CC_ADAPTER_HOST` | `0.0.0.0` | |
| `CC_ADAPTER_PORT` | `8080` | |
| `CC_ADAPTER_LOG_LEVEL` | `INFO` | |
| `CC_ADAPTER_LOG_FORMAT` | `console` | or `json` |
| `CC_ADAPTER_ADMIN_PASSWORD` | — | Admin panel password |

## Architecture

```
POST /v1/messages → providers/anthropic/request.py → command_code/client.py
POST /v1/chat/completions → providers/openai/request.py → command_code/client.py
Both translate to CC /alpha/generate body, stream SSE back.
```

- **Two translator pairs** in `providers/anthropic/` and `providers/openai/` (request→CC, response←CC); shared code in `providers/shared/`, `command_code/`, `core/`.
- **Singletons** (`config`, `client`, `translators`) owned by `core/runtime.py`.
- **Retry**: Shared `retry_on_empty()` in `core/retry.py` — retries once on empty upstream response (non-stream only). OpenAI streaming has unique buffering logic in `providers/openai/router.py`.
- **Admin auth**: HMAC-signed token in `core/auth.py` (not JWT); embeds `exp` + password hash prefix. API access validation also in `core/auth.py:check_api_access()`.
- **ID generation**: `generate_id(prefix, length)` in `core/utils.py`.
- **Tool blocks**: `make_tool_call_block()` / `make_tool_result_block()` in `providers/shared/tool_mapping.py`.
- **Version checker**: Background npm polling (`registry.npmjs.org/command-code/latest`), cached 30min, fallback `0.25.2`. See `core/version_checker.py`.

## Translation quirks

**OpenAI:**
- Model mapping via `MODEL_PROVIDER_MAP` (`providers/shared/model_mapping.py`): bare names → canonical CC IDs (e.g. `step-3-5-flash` → `stepfun/Step-3.5-Flash`). Unknown pass through.
- Silently drops: `top_p`, `stop`, `n`, `presence_penalty`, `frequency_penalty`, `user`, `response_format`.
- System prompt → top-level `system` field. `tool` role → `tool-call`/`tool-result` content blocks.
- Tool params: `filePath`/`oldString`/`newString` ↔ `path`/`old_str`/`new_str` (`providers/shared/tool_mapping.py`).
- `reasoning_effort`: clamped to model's supported range via `clamp_reasoning_effort()`. No prompt injection.

**Anthropic:**
- `thinking.budget_tokens` → `reasoning_effort`: `<4K=low, <8K=medium, <16K=high, >=16K=xhigh` (then clamped per model).
- Content blocks: `tool_use`→`tool-call`, `tool_result`→`tool-result`; `image`→warn+skip; `thinking`→pass.
- Auth: `x-api-key` or `Authorization: Bearer`.
- Unsupported: `top_p`, `top_k`, `stop_sequences`, `metadata`.

## Testing

- **Unit tests**: `pytest` + `pytest-asyncio`. Async tests need `@pytest.mark.asyncio`. Uses `ASGITransport(app=app)` — no real HTTP or CC API key.
- **e2e tests**: `tests/e2e_test.sh` (7 scenarios via Docker). Run: `CC_ADAPTER_KEY=<key> bash tests/e2e_test.sh`.
- **Known flaky**: `tests/test_main_auth.py:38 test_chat_completions_with_invalid_access_key` (cross-test singleton contamination).
- **Formatter**: black (line-length 120). No linter/typechecker.

## Docker

```bash
docker build -t dgqyushen/command-code-proxy:latest .
# Port conflict? Create docker-compose.override.yml mapping 8081:8080
docker compose up -d
```

## End-of-work checklist

1. `poetry run pytest tests/` — all pass
2. `docker build` — image builds
3. `docker compose up -d` — container starts
4. `CC_ADAPTER_KEY=<key> bash tests/e2e_test.sh` — 7/7 scenarios pass (重点测试容器)
