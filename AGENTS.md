# CC-Adapter — Agent Guide

## Commands

```bash
poetry install                        # install deps
poetry run pytest                     # run full test suite
poetry run pytest tests/test_tool_mapping.py -v  # single test file
poetry run black .                    # format (line-length 120)
poetry run python -m cc_adapter       # dev server (port 8080, or $CC_ADAPTER_PORT)
poetry run cc-adapter                 # same, via pyproject.toml scripts
bash run.sh                           # alternative: sources .env, runs uvicorn directly
docker build -t dgqyushen/command-code-proxy:latest .
docker compose up -d                  # docker-compose.yml + optional docker-compose.override.yml
```

**Version**: `VERSION` in `core/constants.py:13` is the single source of truth. Both `main.py` and `admin/router.py` import it. Bump when releasing.

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
| `CC_ADAPTER_HTTP_MAX_CONNECTIONS` | `200` | |
| `CC_ADAPTER_HTTP_MAX_KEEPALIVE_CONNECTIONS` | `50` | |
| `CC_ADAPTER_HTTP2` | `false` | |

## Architecture

```
POST /v1/messages → providers/anthropic/request.py → command_code/client.py
POST /v1/chat/completions → providers/openai/request.py → command_code/client.py
Both translate to CC /alpha/generate body, stream SSE back.
```

- **Two translator pairs** in `providers/anthropic/` and `providers/openai/` (request→CC, response←CC); shared code in `providers/shared/`, `command_code/`, `core/`.
- **Singletons** owned by `core/runtime.py`: `_config`, `_cc_client`, translator instances (lazy init via `get_*()`). Also `_version_checker` and `_model_fetcher`.
- **`get_or_create_client()`** at `runtime.py:41` — auto-creates a client with `AppConfig()` defaults if `init()` hasn't been called, logging a warning. Used by all routers when no client is available.
- **Auth headers**: `core/headers.py` — `extract_token()` (Bearer/x-api-key), `auth_error_response(protocol)` (401), `missing_key_response(protocol)` (401). Both response helpers branch on `protocol: "openai" | "anthropic"` for correct error shape.
- **Retry**: `core/retry.py` — `retry_on_empty()` for non-streaming (retries once on empty upstream response), `stream_with_retry()` for streaming (same retry logic + optional error event emission).
- **Admin auth**: HMAC-signed token in `core/auth.py` (not JWT); embeds `exp` + password hash prefix. API access validation at `core/auth.py:check_api_access()`.
- **ID generation**: `generate_id(prefix, length)` in `core/utils.py`.
- **Constants**: `core/constants.py` — `STREAMING_HEADERS`, `NPM_URL`, `NPM_CACHE_TTL`, `NPM_ERROR_BACKOFF`, `VERSION`.
- **Version checker**: Background npm polling, cached 30min, fallback `0.25.2` (env `CC_ADAPTER_DEFAULT_VERSION`). See `core/version_checker.py`. Tests must set `_last_fetch_time = None` (not `0.0`) to guarantee cache invalidation.
- **Model fetcher**: `core/model_fetcher.py` — fetches models/reasoning-efforts from CC API, feeds into `MODEL_PROVIDER_MAP` and `MODEL_REASONING_EFFORTS_MAP` via `refresh_maps()`.

## Translation quirks

**Shared (`providers/shared/`):**
- `model_mapping.py`: `MODEL_PROVIDER_MAP` — bare names → canonical CC IDs. `clamp_reasoning_effort()` — nearest-higher clamping per model's supported range (from `MODEL_REASONING_EFFORTS_MAP`). Maps are mutable at runtime via `refresh_maps()`.
- `tool_mapping.py`: `normalize_schema()` (filePath↔path), `normalize_args()` (path/old_str/new_str→filePath/oldString/newString for file tools), `translate_tool_choice()` (auto/none/required↔type), `make_tool_call_block()`/`make_tool_result_block()`.

**OpenAI:**
- Model mapping: bare names → canonical CC IDs (e.g. `step-3-5-flash` → `stepfun/Step-3.5-Flash`). Unknown pass through.
- Silently drops: `top_p`, `stop`, `n`, `presence_penalty`, `frequency_penalty`, `user`, `response_format`.
- System prompt → top-level `system` field. `tool` role → `tool-call`/`tool-result` content blocks.
- `reasoning_effort`: clamped per model via `clamp_reasoning_effort()`. No prompt injection.

**Anthropic:**
- `thinking.budget_tokens` → `reasoning_effort`: `<4K=low, <8K=medium, <16K=high, >=16K=xhigh` (then clamped per model). Returns `None` when `thinking.enabled` without `budget_tokens`.
- Content blocks: `tool_use`→`tool-call`, `tool_result`→`tool-result`; `image`→warn+skip; `thinking`→pass.
- Auth: `x-api-key` or `Authorization: Bearer`.
- Unsupported: `top_p`, `top_k`, `stop_sequences`, `metadata`.

**Responses API (`providers/openai/responses_*.py`):**
- Converts `input` + `instructions` to CC `messages` format. `previous_response_id` unsupported (returns error).
- `reasoning.effort` clamped same as chat completions.

## Testing

- **Unit tests**: `pytest` + `pytest-asyncio`. Async tests need `@pytest.mark.asyncio`. Uses `ASGITransport(app=app)` + `respx` for HTTP mocking — no real HTTP or CC API key.
- **e2e tests**: `tests/e2e_test.sh` (7 scenarios via Docker). Run: `CC_ADAPTER_KEY=<key> bash tests/e2e_test.sh`.
- **Known flaky**: `tests/test_main_auth.py:38 test_chat_completions_with_invalid_access_key` (cross-test singleton contamination in `runtime.py`).
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
