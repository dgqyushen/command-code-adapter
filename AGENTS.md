# CC-Adapter — Agent Guide

## Commands

```bash
poetry install                    # install deps
poetry run pytest                 # run all tests (150 tests)
poetry run black .                # format (line-length 120)
poetry run python -m cc_adapter   # start dev server (or: run.sh)
docker build -t dgqyushen/command-code-proxy:latest .
docker compose up -d
```

## Entrypoints

- CLI: `cc_adapter/__main__.py` → `cc_adapter/main.py:run()` → uvicorn
- Import: `from cc_adapter.main import app` (FastAPI app)
- Routes: `POST /v1/chat/completions` (OpenAI), `POST /v1/messages` (Anthropic)

## Config via pydantic-settings (env prefix: `CC_ADAPTER_`)

| Env var | Field | Type |
|---|---|---|
| `CC_ADAPTER_CC_API_KEY` | `cc_api_key` | `str \| list[str]` — JSON array supported: `["k1","k2"]` |
| `CC_ADAPTER_CC_BASE_URL` | `cc_base_url` | default `https://api.commandcode.ai` |
| `CC_ADAPTER_DEFAULT_MODEL` | `default_model` | default `deepseek/deepseek-v4-flash` |

All fields in `config.py:AppConfig`. Uses `env_file=".env"` — config is loaded at import via lazy module-level singletons in `main.py`.

## Architecture

```
POST /v1/messages                     POST /v1/chat/completions
  → anthropic/                          → translator/ (OpenAI)
      request.py (Anthropic→CC)           request.py (OpenAI→CC)
      response.py (CC→Anthropic)           response.py (CC→OpenAI)
  → CommandCodeClient.generate()        → CommandCodeClient.generate()
```

- **Two independent translators**: `anthropic/` and `translator/` share no code, no dependency between them.
- **Singletons**: `_config`, `_cc_client`, `_request_translator` are module-level, lazy-init in `main.py`. Admin can swap at runtime via `admin/state.py`.
- **Retry**: Both OpenAI and Anthropic paths retry once on empty upstream response.
- **Admin auth**: HMAC-signed token (not JWT). Token embeds `exp` + password hash prefix; validated via `hmac.compare_digest`.

## Translation quirks — OpenAI

- **Model auto-prefixing**: bare names in `MODEL_PROVIDER_MAP` (e.g. `deepseek-v4-flash`) get `deepseek/` prepended. See `translator/request.py`.
- **Unsupported params silently dropped**: `top_p`, `stop`, `n`, `presence_penalty`, `frequency_penalty`, `user`, `response_format` → logged as warning.
- **System prompt** extracted from messages, passed as top-level `system` field.
- **`tool` role messages** rewritten to `user` role with `tool-call`/`tool-result` content blocks.
- **Tool param mapping**: `filePath`/`oldString`/`newString` ↔ `path`/`old_str`/`new_str` in `translator/tool_mapping.py`.
- **`reasoning_effort`**: deepseek-v4 models map `xhigh`/`max` → `max` with a special verbose prompt (`REASONING_EFFORT_MAX`). Other models get simple instruction injection from `REASONING_EFFORT_MAP`. Off mode strips `reasoning-delta` from response.

## Translation quirks — Anthropic

- **All fields independent** from OpenAI translator — `cc_adapter/anthropic/` has its own models, request, and response.
- **thinking.budget_tokens** → `reasoning_effort`: <4K=low, <8K=medium, <16K=high, >=16K=xhigh
- **Content blocks**: `tool_use` → `tool-call`, `tool_result` → `tool-result`, `image` → warn+skip
- **Auth**: supports `x-api-key` header (Anthropic convention) or `Authorization: Bearer`
- **Unsupported params**: `top_p`, `top_k`, `stop_sequences`, `metadata` → logged as warning

## Testing

- `pytest` + `pytest-asyncio` — all async tests need `@pytest.mark.asyncio`
- Tests use `ASGITransport(app=app)` — no real HTTP, no CC API key required
- No linter/typechecker configured; only formatter is black (line-length 120)
- One pre-existing flaky test: `test_chat_completions_with_invalid_access_key`

## Admin panel

- SPA at `/admin` — static files in `admin/static/`
- Admin API at `/admin/api/*` — model list from `MODEL_PROVIDER_MAP`, config updates via `PUT /admin/api/config`
- Runtime config changes call `admin/state.py:init()` to recreate `CommandCodeClient`
- Usage dashboard queries `/alpha/whoami`, `/alpha/billing/credits`, `/alpha/billing/subscriptions`, `/alpha/usage/summary`

## Worktrees

Worktree root at `.worktrees/` (gitignored). Create new worktrees with:
```bash
git worktree add .worktrees/<name> -b <branch>
```

## Docker verification

After any significant code change, run `docker build -t dgqyushen/command-code-proxy:latest . && docker compose up -d` to verify the container builds and starts.
