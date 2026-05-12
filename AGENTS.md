# CC-Adapter — Agent Guide

## Commands

```bash
poetry install                    # install deps
poetry run pytest                 # run all 167 tests
poetry run black .                # format (line-length 120)
poetry run python -m cc_adapter   # start dev server (port 8080, or set CC_ADAPTER_PORT)
docker build -t dgqyushen/command-code-proxy:latest .
docker compose up -d              # compose.yml + optional compose.override.yml
```

## Entrypoints & Routes

- CLI: `cc_adapter/__main__.py` → `main.py:run()` → uvicorn
- Import: `from cc_adapter.main import app` (FastAPI app)
- `POST /v1/chat/completions` — OpenAI chat in `main.py` (inline handler)
- `POST /v1/messages` — Anthropic chat in `cc_adapter/anthropic/router.py`
- `GET /v1/models` — OpenAPI model listing in `main.py` (hardcoded 19 models from `cc_adapter/models_data.py`)
- `GET /admin/api/models` — admin model list, no auth

## Config (env prefix `CC_ADAPTER_`)

| Env var | Field | Type |
|---|---|---|
| `CC_ADAPTER_CC_API_KEY` | `cc_api_key` | `str \| list[str]` — JSON array supported: `["k1","k2"]` |
| `CC_ADAPTER_ACCESS_KEY` | `access_key` | Bearer token for auth (all endpoints) |
| `CC_ADAPTER_CC_BASE_URL` | `cc_base_url` | default `https://api.commandcode.ai` |
| `CC_ADAPTER_DEFAULT_MODEL` | `default_model` | default `deepseek/deepseek-v4-flash` |
| `CC_ADAPTER_PORT` | `port` | default `8080` |
| `CC_ADAPTER_ADMIN_PASSWORD` | `admin_password` | Admin login password |

All fields in `config.py:AppConfig`. Uses `.env` file. Config loaded lazily as module-level singletons in `main.py`.

## Architecture

```
POST /v1/messages                     POST /v1/chat/completions
  → anthropic/                          → openai/ (OpenAI)
      request.py (Anthropic→CC)           request.py (OpenAI→CC)
      response.py (CC→Anthropic)           response.py (CC→OpenAI)
  → CommandCodeClient.generate()        → CommandCodeClient.generate()
```

- **Two translators** in `anthropic/` and `openai/`; shared utilities in `_shared.py`, `_tool_mapping.py`, `_body.py`.
- **Singletons**: `_config`, `_cc_client`, `_request_translator` in `main.py`; admin can swap via `admin/state.py:init()`.
- **Retry**: Both paths retry once on empty upstream response.
- **Admin auth**: HMAC-signed token (not JWT); embeds `exp` + password hash prefix.

## Translation quirks — OpenAI

- **Model canonical IDs**: `MODEL_PROVIDER_MAP` in `cc_adapter/_shared.py` maps bare names (e.g. `step-3-5-flash`) to full CC API IDs (`stepfun/Step-3.5-Flash`). Unknown models pass through unchanged.
- **Unsupported params silently dropped**: `top_p`, `stop`, `n`, `presence_penalty`, `frequency_penalty`, `user`, `response_format`.
- **System prompt** extracted from messages, passed as top-level `system` field.
- **`tool` role messages** rewritten to `user` role with `tool-call`/`tool-result` content blocks.
- **Tool param mapping**: `filePath`/`oldString`/`newString` ↔ `path`/`old_str`/`new_str` in `cc_adapter/_tool_mapping.py`.
- **`reasoning_effort`**: deepseek-v4 models map `xhigh`/`max` → `max` with special verbose prompt (`REASONING_EFFORT_MAX`). Other models get simple instruction injection.

## Translation quirks — Anthropic

- **Independent translator** — own models, request, response under `cc_adapter/anthropic/`; imports `_tool_mapping.py`, `_shared.py`.
- **thinking.budget_tokens** → `reasoning_effort`: <4K=low, <8K=medium, <16K=high, >=16K=xhigh.
- **Content blocks**: `tool_use` → `tool-call`, `tool_result` → `tool-result`, `image` → warn+skip, `thinking` → pass.
- **Auth**: `x-api-key` or `Authorization: Bearer`.
- **Unsupported**: `top_p`, `top_k`, `stop_sequences`, `metadata`.

## Testing

- **Unit tests**: `pytest` + `pytest-asyncio`. Async tests need `@pytest.mark.asyncio`.
- Tests use `ASGITransport(app=app)` — no real HTTP, no CC API key.
- **e2e tests**: `tests/e2e_test.sh` — tests 6 scenarios through Docker:
  `/v1/models`, OpenAI streaming, Anthropic streaming, OpenAI tool calls, Anthropic tool calls, Anthropic multi-turn tool_result.
  Run with `CC_ADAPTER_KEY=<access_key> bash tests/e2e_test.sh`.
- **Known flaky**: `test_chat_completions_with_invalid_access_key` (cross-test singleton contamination).
- **Formatter**: black (line-length 120). No linter/typechecker.
- **CC API model name must use canonical IDs** (e.g. `stepfun/Step-3.5-Flash`, not `step-3-5-flash`). The adapter's `MODEL_PROVIDER_MAP` handles this mapping automatically.

## Docker

```bash
# Build
docker build -t dgqyushen/command-code-proxy:latest .

# Start — 8080 may be occupied; create docker-compose.override.yml to use 8081:
# services:
#   cc-adapter:
#     ports:
#       - "8081:8080"
docker compose up -d
```

After significant code changes: build → compose up → run `e2e_test.sh` to verify.

## End-of-work checklist

1. `poetry run pytest tests/` — unit tests pass (167 tests, 1 known flaky)
2. `docker build` — image builds
3. `docker compose up -d` — container starts
4. `CC_ADAPTER_KEY=<key> bash tests/e2e_test.sh` — all 6 e2e scenarios pass (重点测试容器)
