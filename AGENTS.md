# CC-Adapter — Agent Guide

## Commands

```bash
poetry install                    # install deps
poetry run pytest                 # run full test suite
poetry run black .                # format (line-length 120)
poetry run python -m cc_adapter   # start dev server (port 8080, or set CC_ADAPTER_PORT)
docker build -t dgqyushen/command-code-proxy:latest .
docker compose up -d              # compose.yml + optional compose.override.yml
```

## Entrypoints & Routes

- CLI: `cc_adapter/__main__.py` → `main.py:run()` → uvicorn
- Import: `from cc_adapter.main import app` (FastAPI app)
- `POST /v1/chat/completions` — OpenAI chat in `providers/openai/router.py`
- `POST /v1/messages` — Anthropic chat in `providers/anthropic/router.py`
- `GET /v1/models` — OpenAPI model listing in `main.py` (hardcoded 19 models from `catalog/models_data.py`)
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

All fields in `core/config.py:AppConfig`. Uses `.env` file. Config loaded eagerly at module import time.

## Architecture

```
POST /v1/messages                     POST /v1/chat/completions
  → providers/anthropic/                → providers/openai/
      request.py (Anthropic→CC)           request.py (OpenAI→CC)
      response.py (CC→Anthropic)           response.py (CC→OpenAI)
  → command_code/client.py             → command_code/client.py
```

- **Two translators** in `providers/anthropic/` and `providers/openai/`; shared utilities in `providers/shared/`, `command_code/`, `core/`.
- **Singletons**: `config`, `client`, `translators` owned by `core/runtime.py`.
- **Retry**: Both paths retry once on empty upstream response. OpenAI retry in `providers/openai/router.py`.
- **Admin auth**: HMAC-signed token in `core/auth.py` (not JWT); embeds `exp` + password hash prefix.

## Translation quirks — OpenAI

- **Model canonical IDs**: `MODEL_PROVIDER_MAP` in `providers/shared/model_mapping.py` maps bare names (e.g. `step-3-5-flash`) to full CC API IDs (`stepfun/Step-3.5-Flash`). Unknown models pass through unchanged.
- **Unsupported params silently dropped**: `top_p`, `stop`, `n`, `presence_penalty`, `frequency_penalty`, `user`, `response_format`.
- **System prompt** extracted from messages, passed as top-level `system` field.
- **`tool` role messages** kept as `tool` role with `tool-call`/`tool-result` content blocks.
- **Tool param mapping**: `filePath`/`oldString`/`newString` ↔ `path`/`old_str`/`new_str` in `providers/shared/tool_mapping.py`.
- **`reasoning_effort`**: deepseek-v4 models map `xhigh`/`max` → `max` with special verbose prompt (`REASONING_EFFORT_MAX`). Other models get simple instruction injection.

## Translation quirks — Anthropic

- **Independent translator** — own models, request, response under `providers/anthropic/`; imports `providers/shared/tool_mapping.py`, `providers/shared/model_mapping.py`.
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

1. `poetry run pytest tests/` — unit tests pass
2. `docker build` — image builds
3. `docker compose up -d` — container starts
4. `CC_ADAPTER_KEY=<key> bash tests/e2e_test.sh` — all 6 e2e scenarios pass (重点测试容器)
