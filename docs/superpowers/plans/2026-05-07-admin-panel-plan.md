# Admin Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a web-based admin panel to CC Adapter for visual config editing, endpoint testing, and API key verification.

**Architecture:** FastAPI serves static HTML/CSS/JS at `/admin/` and provides REST API endpoints at `/admin/api/*`. Auth is password-based with in-memory token. Config changes write to `.env` and hot-reload at runtime.

**Tech Stack:** Python + FastAPI (backend), vanilla HTML/CSS/JS (frontend, no build tools)

**Spec:** `docs/superpowers/specs/2026-05-07-admin-panel-design.md`

---

## File Structure

```
cc_adapter/
├── admin/
│   ├── __init__.py                # Empty module init
│   ├── router.py                  # Admin API endpoints
│   └── auth.py                    # Auth logic (password check, token management)
├── main.py                        # MODIFY: register admin router + static files
├── config.py                      # MODIFY: add admin_password field
├── admin/
│   └── static/
│       ├── admin.html             # CREATE: single-page app HTML
│       ├── admin.css              # CREATE: styles with light/dark theme
│       └── admin.js               # CREATE: all frontend logic
tests/
└── test_admin_router.py           # CREATE: admin API tests
.env.example                       # MODIFY: add CC_ADMIN_PASSWORD
```

---

### Task 1: Add admin_password to AppConfig

**Files:**
- Modify: `cc_adapter/config.py`

- [ ] **Step 1: Add admin_password field**

Edit `cc_adapter/config.py`:

```python
class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CC_ADAPTER_", env_file=".env", extra="ignore")

    host: str = "0.0.0.0"
    port: int = 8080
    log_level: str = "INFO"
    cc_api_key: str = ""
    cc_base_url: str = "https://api.commandcode.ai"
    admin_password: str = ""
```

This maps to env var `CC_ADAPTER_ADMIN_PASSWORD` (or `CC_ADMIN_PASSWORD` via `.env` file since pydantic-settings also reads field names from `.env`).

- [ ] **Step 2: Verify it loads correctly**

Run: `python -c "from cc_adapter.config import AppConfig; c = AppConfig(); print(c.admin_password)"`
Expected: empty string (default)

- [ ] **Step 3: Commit**

```bash
git add cc_adapter/config.py
git commit -m "feat: add admin_password to AppConfig"
```

---

### Task 2: Create auth module

**Files:**
- Create: `cc_adapter/admin/__init__.py`
- Create: `cc_adapter/admin/auth.py`
- Create: `tests/test_admin_auth.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_admin_auth.py`:

```python
from cc_adapter.admin.auth import set_password, validate_token, generate_token


def test_no_password_always_valid():
    set_password("")
    token = "anything"
    assert validate_token(token) is True


def test_with_password_requires_matching_token():
    set_password("mysecret")
    token = generate_token()
    assert validate_token(token) is True
    assert validate_token("wrong") is False


def test_generate_token_returns_hex():
    set_password("pw")
    token = generate_token()
    assert len(token) == 64  # 32 bytes hex
    assert all(c in "0123456789abcdef" for c in token)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
poetry run pytest tests/test_admin_auth.py -v
```
Expected: ImportError — module doesn't exist yet

- [ ] **Step 3: Write minimal implementation**

Create `cc_adapter/admin/__init__.py` (empty file).

Create `cc_adapter/admin/auth.py`:

```python
from __future__ import annotations

import secrets

_admin_token: str | None = None
_admin_password: str = ""


def set_password(password: str) -> None:
    global _admin_password
    _admin_password = password


def generate_token() -> str:
    global _admin_token
    _admin_token = secrets.token_hex(32)
    return _admin_token


def validate_token(token: str) -> bool:
    if not _admin_password:
        return True
    return token == _admin_token
```

- [ ] **Step 4: Run test to verify it passes**

```bash
poetry run pytest tests/test_admin_auth.py -v
```
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add cc_adapter/admin/ tests/test_admin_auth.py
git commit -m "feat: add admin auth module with token management"
```

---

### Task 3: Create admin state holder (avoid circular import)

**Files:**
- Create: `cc_adapter/admin/state.py`

Main.py imports admin router, and router needs access to `config` and `cc_client`. Creating a state module breaks the circular dependency.

- [ ] **Step 1: Create state.py**

Create `cc_adapter/admin/state.py`:

```python
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
```

- [ ] **Step 2: Verify import works**

```bash
poetry run python -c "from cc_adapter.admin.state import config, cc_client, init; print('OK')"
```
Expected: OK

- [ ] **Step 3: Commit**

```bash
git add cc_adapter/admin/state.py
git commit -m "feat: add admin state module to avoid circular imports"
```

---

### Task 4: Create admin API router

**Files:**
- Create: `cc_adapter/admin/router.py`
- Test: `tests/test_admin_router.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_admin_router.py`:

```python
import pytest
from httpx import ASGITransport, AsyncClient
from cc_adapter.main import app
from cc_adapter.admin.auth import set_password


@pytest.fixture(autouse=True)
def setup_auth():
    set_password("admin123")


@pytest.mark.asyncio
async def test_login_success():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/admin/api/login", json={"password": "admin123"})
    assert resp.status_code == 200
    data = resp.json()
    assert "token" in data


@pytest.mark.asyncio
async def test_login_failure():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/admin/api/login", json={"password": "wrong"})
    assert resp.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

```bash
poetry run pytest tests/test_admin_router.py -v
```
Expected: ImportError or 404 — router not registered yet

- [ ] **Step 3: Write implementation**

Create `cc_adapter/admin/router.py`:

```python
from __future__ import annotations

import json
import os
import time
import logging
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from cc_adapter.admin.auth import generate_token, validate_token
from cc_adapter.admin.state import get_config, get_client, init as state_init
from cc_adapter.client import CommandCodeClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/api")
_start_time = time.time()


class LoginRequest(BaseModel):
    password: str


class LoginResponse(BaseModel):
    token: str


class ConfigUpdate(BaseModel):
    cc_api_key: str | None = None
    cc_base_url: str | None = None
    host: str | None = None
    port: int | None = None
    log_level: str | None = None


async def verify_auth(authorization: str | None = None):
    cfg = get_config()
    if not cfg or not cfg.admin_password:
        return True
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = authorization[7:]
    if not validate_token(token):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True


@router.post("/login")
async def login(req: LoginRequest):
    cfg = get_config()
    if not cfg or not cfg.admin_password:
        return LoginResponse(token="")
    if req.password != cfg.admin_password:
        raise HTTPException(status_code=401, detail="Invalid password")
    token = generate_token()
    return LoginResponse(token=token)


@router.get("/config")
async def get_config_endpoint(_=Depends(verify_auth)):
    cfg = get_config()
    return {
        "cc_api_key": "****" if cfg and cfg.cc_api_key else "",
        "cc_base_url": cfg.cc_base_url if cfg else "",
        "host": cfg.host if cfg else "",
        "port": cfg.port if cfg else 8080,
        "log_level": cfg.log_level if cfg else "INFO",
        "admin_password_configured": bool(cfg and cfg.admin_password),
    }


@router.put("/config")
async def update_config(update: ConfigUpdate, _=Depends(verify_auth)):
    _update_env_file(update)
    _apply_config_update(update)
    return await get_config_endpoint()


@router.post("/verify-key")
async def verify_key(_=Depends(verify_auth)):
    cfg = get_config()
    if not cfg or not cfg.cc_api_key:
        return {"valid": False, "message": "No API Key configured"}
    test_client = CommandCodeClient(base_url=cfg.cc_base_url, api_key=cfg.cc_api_key, timeout=10.0)
    try:
        test_body = {
            "config": {"env": "adapter", "workingDir": "/tmp", "date": "2026-01-01T00:00:00Z", "environment": "production", "structure": [], "isGitRepo": False, "currentBranch": "main", "mainBranch": "main", "gitStatus": "clean", "recentCommits": []},
            "memory": "",
            "taste": None,
            "skills": None,
            "permissionMode": "standard",
            "params": {"model": "claude-sonnet-4-6", "messages": [{"role": "user", "content": "ping"}], "max_tokens": 10, "stream": False},
        }
        async for _ in test_client.generate(test_body):
            break
        return {"valid": True, "message": "API Key is valid"}
    except Exception as e:
        return {"valid": False, "message": str(e)}


@router.get("/health")
async def admin_health(_=Depends(verify_auth)):
    cfg = get_config()
    return {
        "status": "ok",
        "version": "0.1.0",
        "uptime": int(time.time() - _start_time),
        "cc_api_key_configured": bool(cfg and cfg.cc_api_key),
    }


def _update_env_file(update: ConfigUpdate) -> None:
    env_path = Path(".env")
    if not env_path.exists():
        env_path.write_text("")
    lines = env_path.read_text().splitlines(keepends=True)
    field_map = {
        "cc_api_key": "CC_API_KEY",
        "cc_base_url": "CC_BASE_URL",
        "host": "CC_ADAPTER_HOST",
        "port": "CC_ADAPTER_PORT",
        "log_level": "CC_ADAPTER_LOG_LEVEL",
    }
    update_map = update.model_dump(exclude_none=True)
    existing_keys = set()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if "=" not in stripped or stripped.startswith("#"):
            continue
        key = stripped.split("=", 1)[0].strip()
        for field_name, env_key in field_map.items():
            if key == env_key and field_name in update_map:
                value = update_map[field_name]
                lines[i] = f"{env_key}={value}\n"
                existing_keys.add(field_name)
    for field_name, env_key in field_map.items():
        if field_name in update_map and field_name not in existing_keys:
            lines.append(f"{env_key}={update_map[field_name]}\n")
    env_path.write_text("".join(lines))


def _apply_config_update(update: ConfigUpdate) -> None:
    from cc_adapter.admin.state import init
    update_dict = update.model_dump(exclude_none=True)
    cfg = get_config()
    if cfg is None:
        return

    changed_client = False
    if "cc_api_key" in update_dict:
        cfg.cc_api_key = update_dict["cc_api_key"]
        changed_client = True
    if "cc_base_url" in update_dict:
        cfg.cc_base_url = update_dict["cc_base_url"]
        changed_client = True
    if "host" in update_dict:
        cfg.host = update_dict["host"]
    if "port" in update_dict:
        cfg.port = update_dict["port"]
    if "log_level" in update_dict:
        cfg.log_level = update_dict["log_level"]

    if changed_client:
        new_client = CommandCodeClient(base_url=cfg.cc_base_url, api_key=cfg.cc_api_key)
        init(cfg, new_client)
```

- [ ] **Step 4: Run tests**

```bash
poetry run pytest tests/test_admin_router.py -v
```
Expected: 2 passed

- [ ] **Step 5: Add more tests**

Append to `tests/test_admin_router.py`:

```python
@pytest.mark.asyncio
async def test_get_config_requires_auth():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/admin/api/config")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_config_returns_fields():
    set_password("admin123")
    from cc_adapter.admin.auth import generate_token
    my_token = generate_token()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/admin/api/config", headers={"Authorization": f"Bearer {my_token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "cc_api_key" in data
    assert "cc_base_url" in data
    assert "host" in data
    assert "port" in data
    assert "log_level" in data
```

- [ ] **Step 6: Run all tests**

```bash
poetry run pytest tests/test_admin_router.py tests/test_admin_auth.py -v
```
Expected: all passed

- [ ] **Step 7: Commit**

```bash
git add cc_adapter/admin/router.py tests/test_admin_router.py
git commit -m "feat: add admin API router with config, login, verify-key, health endpoints"
```

---

### Task 5: Register admin router and static files in main.py

**Files:**
- Modify: `cc_adapter/main.py`

- [ ] **Step 1: Modify main.py**

Edit `cc_adapter/main.py` to:
1. Initialize admin state with config and client
2. Mount static files at `/admin/`
3. Pass config.admin_password to auth module on startup

Add imports at top:
```python
from fastapi.staticfiles import StaticFiles
from cc_adapter.admin import router as admin_router
from cc_adapter.admin.auth import set_password
from cc_adapter.admin.state import init as admin_init, get_client as get_admin_client
```

Add state init + static files mount + router include after `app = FastAPI(...)`:
```python
admin_init(config, cc_client)

admin_static = StaticFiles(directory=Path(__file__).parent / "admin" / "static", html=True)
app.mount("/admin", admin_static, name="admin_static")
app.include_router(admin_router.router)
```

Add `set_password(config.admin_password)` in the `lifespan` function:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=getattr(logging, config.log_level.upper(), logging.INFO))
    set_password(config.admin_password)
    logger.info("CC Adapter starting — CC API: %s", config.cc_base_url)
    if not config.cc_api_key:
        logger.warning("CC_API_KEY is not set. Set it via environment variable or .env file.")
    yield
```

Add `from pathlib import Path` to imports.

The full modified file:

```python
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from cc_adapter.config import AppConfig
from cc_adapter.client import CommandCodeClient
from cc_adapter.translator.request import RequestTranslator
from cc_adapter.translator.response import translate_stream, collect_and_translate_nonstream
from cc_adapter.errors import AdapterError, AuthenticationError
from cc_adapter.models.openai import ChatCompletionRequest
from cc_adapter.admin import router as admin_router
from cc_adapter.admin.auth import set_password
from cc_adapter.admin.state import init as admin_init, get_client as get_admin_client

logger = logging.getLogger(__name__)
config = AppConfig()
cc_client = CommandCodeClient(base_url=config.cc_base_url, api_key=config.cc_api_key)
request_translator = RequestTranslator()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=getattr(logging, config.log_level.upper(), logging.INFO))
    set_password(config.admin_password)
    logger.info("CC Adapter starting — CC API: %s", config.cc_base_url)
    if not config.cc_api_key:
        logger.warning("CC_API_KEY is not set. Set it via environment variable or .env file.")
    yield


app = FastAPI(title="Command Code Adapter", version="0.1.0", lifespan=lifespan)

admin_init(config, cc_client)

admin_static = StaticFiles(directory=Path(__file__).parent / "admin" / "static", html=True)
app.mount("/admin", admin_static, name="admin_static")
app.include_router(admin_router.router)


@app.exception_handler(AdapterError)
async def adapter_error_handler(request: Request, exc: AdapterError):
    return JSONResponse(status_code=exc.status_code, content=exc.to_openai_error())


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest):
    logger.info("Request: model=%s stream=%s messages=%d tools=%s",
                req.model, req.stream, len(req.messages), "yes" if req.tools else "no")

    cc_body, cc_headers = request_translator.translate(req)
    cc_body["params"]["stream"] = True

    current_client = get_admin_client() or cc_client
    if not current_client.api_key:
        raise AuthenticationError("CC_API_KEY is not configured")

    cc_stream = current_client.generate(cc_body, cc_headers)

    if req.stream:
        return StreamingResponse(
            translate_stream(cc_stream, req.model),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    else:
        result = await collect_and_translate_nonstream(cc_stream, req.model)
        return result


def run():
    import uvicorn
    uvicorn.run(
        "cc_adapter.main:app",
        host=config.host,
        port=config.port,
        log_level=config.log_level.lower(),
    )
```

- [ ] **Step 2: Verify imports work**

```bash
poetry run python -c "from cc_adapter.main import app; print('OK')"
```
Expected: OK (no import errors)

- [ ] **Step 3: Run existing tests to verify nothing broke**

```bash
poetry run pytest tests/ -v
```
Expected: all tests pass

- [ ] **Step 4: Commit**

```bash
git add cc_adapter/main.py
git commit -m "feat: register admin router and static files in main app"
```

---

### Task 5: Create frontend HTML

**Files:**
- Create: `cc_adapter/admin/static/admin.html`

- [ ] **Step 1: Create admin.html**

```html
<!DOCTYPE html>
<html lang="zh-CN" data-theme="light">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CC Adapter Admin</title>
<link rel="stylesheet" href="admin.css">
</head>
<body>
<div id="app">
  <div id="login-overlay" class="hidden">
    <div class="login-box">
      <h2 id="login-title">Admin Login</h2>
      <input type="password" id="login-password" placeholder="Password">
      <button id="login-btn">Login</button>
      <p id="login-error" class="error-text hidden"></p>
    </div>
  </div>
  <nav id="topbar">
    <span class="logo">CC Adapter</span>
    <div class="topbar-actions">
      <select id="lang-switch">
        <option value="zh">中文</option>
        <option value="en">English</option>
      </select>
      <button id="theme-toggle">Dark</button>
    </div>
  </nav>
  <div id="layout">
    <aside id="sidebar">
      <div class="nav-item active" data-tab="dashboard">Dashboard</div>
      <div class="nav-item" data-tab="config">Configuration</div>
      <div class="nav-item" data-tab="playground">Playground</div>
    </aside>
    <main id="content">
      <div id="toast" class="hidden"></div>
      <div id="tab-dashboard" class="tab-content active"></div>
      <div id="tab-config" class="tab-content"></div>
      <div id="tab-playground" class="tab-content"></div>
    </main>
  </div>
</div>
<script src="admin.js"></script>
</body>
</html>
```

- [ ] **Step 2: Create empty CSS placeholder so HTML can load**

```css
/* placeholder - will be filled in Task 6 */
```

- [ ] **Step 3: Create empty JS placeholder**

```javascript
// placeholder - will be filled in Task 7
```

- [ ] **Step 4: Commit**

```bash
git add cc_adapter/admin/static/admin.html
git commit -m "feat: add admin panel HTML structure"
```

---

### Task 6: Create frontend CSS with light/dark theme

**Files:**
- Create: `cc_adapter/admin/static/admin.css`

- [ ] **Step 1: Create admin.css**

```css
:root {
  --bg: #ffffff;
  --bg-secondary: #f5f5f5;
  --bg-tertiary: #e8e8e8;
  --text: #1a1a1a;
  --text-secondary: #666;
  --text-muted: #999;
  --accent: #0066cc;
  --accent-hover: #0052a3;
  --border: #e0e0e0;
  --success: #22c55e;
  --error: #ef4444;
  --warning: #f59e0b;
  --sidebar-width: 200px;
  --topbar-height: 48px;
  --radius: 6px;
}

[data-theme="dark"] {
  --bg: #1a1a1a;
  --bg-secondary: #2d2d2d;
  --bg-tertiary: #383838;
  --text: #e5e5e5;
  --text-secondary: #999;
  --text-muted: #666;
  --accent: #3b82f6;
  --accent-hover: #2563eb;
  --border: #404040;
  --success: #22c55e;
  --error: #ef4444;
  --warning: #f59e0b;
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  background: var(--bg);
  color: var(--text);
  font-size: 14px;
  line-height: 1.5;
}

#app { display: flex; flex-direction: column; min-height: 100vh; }

/* Top Bar */
#topbar {
  height: var(--topbar-height);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  border-bottom: 1px solid var(--border);
  background: var(--bg);
  position: sticky;
  top: 0;
  z-index: 100;
}
.logo { font-weight: 600; font-size: 15px; }
.topbar-actions { display: flex; gap: 8px; align-items: center; }
#lang-switch {
  padding: 4px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--bg);
  color: var(--text);
  font-size: 13px;
  cursor: pointer;
}
#theme-toggle {
  padding: 4px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--bg-secondary);
  color: var(--text);
  font-size: 13px;
  cursor: pointer;
}
#theme-toggle:hover { background: var(--bg-tertiary); }

/* Layout */
#layout { display: flex; flex: 1; }

/* Sidebar */
#sidebar {
  width: var(--sidebar-width);
  border-right: 1px solid var(--border);
  padding: 8px 0;
  flex-shrink: 0;
}
.nav-item {
  padding: 10px 16px;
  cursor: pointer;
  color: var(--text-secondary);
  border-left: 3px solid transparent;
  transition: all 0.15s;
}
.nav-item:hover { background: var(--bg-secondary); color: var(--text); }
.nav-item.active {
  background: var(--bg-secondary);
  color: var(--accent);
  border-left-color: var(--accent);
  font-weight: 500;
}

/* Content */
#content { flex: 1; padding: 24px; overflow-y: auto; }
.tab-content { display: none; }
.tab-content.active { display: block; }

/* Toast */
#toast {
  position: fixed;
  top: 60px;
  left: 50%;
  transform: translateX(-50%);
  padding: 8px 20px;
  border-radius: var(--radius);
  font-size: 13px;
  z-index: 200;
  transition: opacity 0.3s;
}
#toast.hidden { opacity: 0; pointer-events: none; }
#toast.success { background: var(--success); color: white; }
#toast.error { background: var(--error); color: white; }

/* Login Overlay */
#login-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 300;
}
#login-overlay.hidden { display: none; }
.login-box {
  background: var(--bg);
  padding: 32px;
  border-radius: 8px;
  width: 320px;
  box-shadow: 0 4px 24px rgba(0,0,0,0.15);
}
.login-box h2 { margin-bottom: 16px; font-size: 18px; }
.login-box input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  font-size: 14px;
  background: var(--bg);
  color: var(--text);
  margin-bottom: 12px;
}
.login-box button {
  width: 100%;
  padding: 8px;
  border: none;
  border-radius: var(--radius);
  background: var(--accent);
  color: white;
  font-size: 14px;
  cursor: pointer;
}
.login-box button:hover { background: var(--accent-hover); }
.error-text { color: var(--error); font-size: 13px; margin-top: 8px; }
.hidden { display: none; }

/* Cards */
.card {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px;
  margin-bottom: 16px;
}
.card-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.status-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 6px;
}
.status-dot.ok { background: var(--success); }
.status-dot.err { background: var(--error); }

/* Config Form */
.form-group { margin-bottom: 16px; }
.form-group label {
  display: block;
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 4px;
  font-family: monospace;
}
.form-group input, .form-group select {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  font-size: 14px;
  background: var(--bg);
  color: var(--text);
}
.form-group input:focus, .form-group select:focus {
  outline: none;
  border-color: var(--accent);
}
.form-actions { display: flex; gap: 8px; margin-top: 20px; }
.btn {
  padding: 8px 20px;
  border: none;
  border-radius: var(--radius);
  font-size: 14px;
  cursor: pointer;
  transition: opacity 0.15s;
}
.btn:hover { opacity: 0.9; }
.btn-primary { background: var(--accent); color: white; }
.btn-secondary { background: var(--bg-tertiary); color: var(--text); }
.btn-danger { background: var(--error); color: white; }

/* Playground */
.playground-form { margin-bottom: 16px; }
.playground-form .form-group textarea {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  font-size: 14px;
  background: var(--bg);
  color: var(--text);
  font-family: monospace;
  resize: vertical;
  min-height: 100px;
}
.playground-form .form-group textarea:focus { outline: none; border-color: var(--accent); }
.checkbox-row { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.checkbox-row input[type="checkbox"] { width: auto; }
.response-area {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px;
  min-height: 200px;
  max-height: 500px;
  overflow-y: auto;
  font-family: monospace;
  font-size: 13px;
  white-space: pre-wrap;
  word-break: break-all;
}
.response-area.streaming .line { margin-bottom: 4px; }
```

- [ ] **Step 2: Verify HTML loads without errors**

Run the server and check that `/admin/` serves a page with CSS applied.

- [ ] **Step 3: Commit**

```bash
git add cc_adapter/admin/static/admin.css
git commit -m "feat: add admin panel CSS with light/dark theme"
```

---

### Task 7: Create frontend JavaScript

**Files:**
- Create: `cc_adapter/admin/static/admin.js`

- [ ] **Step 1: Create admin.js**

```javascript
// I18n
const i18n = {
  zh: {
    title: "CC Adapter 管理面板",
    loginTitle: "管理员登录",
    loginBtn: "登录",
    loginError: "密码错误",
    loginPlaceholder: "请输入密码",
    dashboard: "状态面板",
    config: "配置编辑",
    playground: "测试面板",
    serverStatus: "服务状态",
    running: "运行中",
    stopped: "未运行",
    apiKey: "API Key",
    configured: "已配置",
    notConfigured: "未配置",
    verify: "验证",
    verifying: "验证中...",
    valid: "有效",
    invalid: "无效",
    save: "保存",
    cancel: "取消",
    saved: "保存成功",
    saveFailed: "保存失败",
    model: "模型",
    messages: "消息",
    stream: "流式输出",
    send: "发送",
    clear: "清空",
    response: "响应",
    configKey: "API Key",
    configBaseUrl: "Base URL",
    configHost: "监听地址",
    configPort: "监听端口",
    configLogLevel: "日志级别",
    themeDark: "Dark",
    themeLight: "Light",
  },
  en: {
    title: "CC Adapter Admin",
    loginTitle: "Admin Login",
    loginBtn: "Login",
    loginError: "Invalid password",
    loginPlaceholder: "Enter password",
    dashboard: "Dashboard",
    config: "Configuration",
    playground: "Playground",
    serverStatus: "Server Status",
    running: "Running",
    stopped: "Stopped",
    apiKey: "API Key",
    configured: "Configured",
    notConfigured: "Not Configured",
    verify: "Verify",
    verifying: "Verifying...",
    valid: "Valid",
    invalid: "Invalid",
    save: "Save",
    cancel: "Cancel",
    saved: "Saved successfully",
    saveFailed: "Save failed",
    model: "Model",
    messages: "Messages",
    stream: "Stream",
    send: "Send",
    clear: "Clear",
    response: "Response",
    configKey: "API Key",
    configBaseUrl: "Base URL",
    configHost: "Host",
    configPort: "Port",
    configLogLevel: "Log Level",
    themeDark: "Dark",
    themeLight: "Light",
  },
};

let lang = localStorage.getItem("cc-admin-lang") || "zh";
let theme = localStorage.getItem("cc-admin-theme") || "light";
let token = localStorage.getItem("cc-admin-token") || null;

function t(key) { return i18n[lang][key] || key; }

function applyLang() {
  document.documentElement.lang = lang;
  document.querySelectorAll("[data-i18n]").forEach(el => {
    el.textContent = t(el.dataset.i18n);
  });
  document.title = t("title");
}

function applyTheme() {
  document.documentElement.dataset.theme = theme;
  document.getElementById("theme-toggle").textContent =
    theme === "dark" ? t("themeLight") : t("themeDark");
}

function toggleTheme() {
  theme = theme === "dark" ? "light" : "dark";
  localStorage.setItem("cc-admin-theme", theme);
  applyTheme();
}

function switchLang(newLang) {
  lang = newLang;
  localStorage.setItem("cc-admin-lang", lang);
  applyLang();
  renderAll();
}

// Toast
let toastTimer = null;
function showToast(msg, type) {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.className = type;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add("hidden"), 3000);
}

// API helpers
async function api(method, path, body) {
  const headers = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const resp = await fetch(path, { method, headers, body: body ? JSON.stringify(body) : undefined });
  if (resp.status === 401 && path !== "/admin/api/login") {
    showLogin();
    throw new Error("Unauthorized");
  }
  return resp;
}

// Auth
function showLogin() {
  token = null;
  localStorage.removeItem("cc-admin-token");
  document.getElementById("login-overlay").classList.remove("hidden");
  document.getElementById("login-error").classList.add("hidden");
}

async function doLogin() {
  const pw = document.getElementById("login-password").value;
  const resp = await api("POST", "/admin/api/login", { password: pw });
  if (resp.status === 401) {
    document.getElementById("login-error").classList.remove("hidden");
    return;
  }
  const data = await resp.json();
  token = data.token;
  localStorage.setItem("cc-admin-token", token);
  document.getElementById("login-overlay").classList.add("hidden");
  renderAll();
}

// Navigation
function switchTab(name) {
  document.querySelectorAll(".nav-item").forEach(el => el.classList.remove("active"));
  document.querySelector(`.nav-item[data-tab="${name}"]`).classList.add("active");
  document.querySelectorAll(".tab-content").forEach(el => el.classList.remove("active"));
  document.getElementById(`tab-${name}`).classList.add("active");
  renderTab(name);
}

// Render by tab
function renderAll() {
  applyLang();
  applyTheme();
  const active = document.querySelector(".nav-item.active");
  if (active) renderTab(active.dataset.tab);
}

function renderTab(name) {
  if (name === "dashboard") renderDashboard();
  else if (name === "config") renderConfig();
  else if (name === "playground") renderPlayground();
}

// Dashboard
async function renderDashboard() {
  const el = document.getElementById("tab-dashboard");
  el.innerHTML = `
    <h2 data-i18n="dashboard">${t("dashboard")}</h2>
    <div class="card-grid" style="margin-top:16px">
      <div class="card">
        <div class="status-dot" id="health-dot"></div>
        <strong data-i18n="serverStatus">${t("serverStatus")}</strong>
        <p id="health-text" style="margin-top:8px;font-size:13px;color:var(--text-secondary)">Loading...</p>
      </div>
      <div class="card">
        <div class="status-dot" id="key-dot"></div>
        <strong data-i18n="apiKey">${t("apiKey")}</strong>
        <p id="key-text" style="margin-top:8px;font-size:13px;color:var(--text-secondary)">Loading...</p>
        <button class="btn btn-secondary" id="verify-key-btn" style="margin-top:12px">${t("verify")}</button>
      </div>
    </div>`;
  loadDashboard();
  document.getElementById("verify-key-btn").onclick = verifyKey;
}

async function loadDashboard() {
  try {
    const resp = await api("GET", "/admin/api/health");
    const data = await resp.json();
    document.getElementById("health-dot").className = "status-dot ok";
    document.getElementById("health-text").textContent =
      `${t("running")} | uptime ${Math.floor(data.uptime / 60)}m`;
    document.getElementById("key-dot").className =
      data.cc_api_key_configured ? "status-dot ok" : "status-dot err";
    document.getElementById("key-text").textContent =
      data.cc_api_key_configured ? t("configured") : t("notConfigured");
  } catch {
    document.getElementById("health-dot").className = "status-dot err";
    document.getElementById("health-text").textContent = t("stopped");
  }
}

async function verifyKey() {
  const btn = document.getElementById("verify-key-btn");
  btn.textContent = t("verifying");
  btn.disabled = true;
  try {
    const resp = await api("POST", "/admin/api/verify-key");
    const data = await resp.json();
    showToast(data.valid ? `${t("apiKey")}: ${t("valid")}` : `${t("apiKey")}: ${t("invalid")} - ${data.message}`,
      data.valid ? "success" : "error");
    loadDashboard();
  } catch { showToast(t("saveFailed"), "error"); }
  btn.textContent = t("verify");
  btn.disabled = false;
}

// Config
let configData = null;

async function renderConfig() {
  const el = document.getElementById("tab-config");
  el.innerHTML = `
    <h2 data-i18n="config">${t("config")}</h2>
    <div class="card" style="margin-top:16px">
      <div class="form-group">
        <label>CC_API_KEY</label>
        <input type="password" id="cfg-key" autocomplete="new-password">
      </div>
      <div class="form-group">
        <label>CC_BASE_URL</label>
        <input type="text" id="cfg-base-url">
      </div>
      <div class="form-group">
        <label>CC_ADAPTER_HOST</label>
        <input type="text" id="cfg-host">
      </div>
      <div class="form-group">
        <label>CC_ADAPTER_PORT</label>
        <input type="number" id="cfg-port">
      </div>
      <div class="form-group">
        <label>CC_ADAPTER_LOG_LEVEL</label>
        <select id="cfg-log-level">
          <option value="DEBUG">DEBUG</option>
          <option value="INFO">INFO</option>
          <option value="WARNING">WARNING</option>
          <option value="ERROR">ERROR</option>
        </select>
      </div>
      <div class="form-actions">
        <button class="btn btn-primary" id="cfg-save">${t("save")}</button>
        <button class="btn btn-secondary" id="cfg-cancel">${t("cancel")}</button>
      </div>
    </div>`;
  loadConfig();
  document.getElementById("cfg-save").onclick = saveConfig;
  document.getElementById("cfg-cancel").onclick = loadConfig;
}

async function loadConfig() {
  try {
    const resp = await api("GET", "/admin/api/config");
    configData = await resp.json();
    document.getElementById("cfg-key").value = configData.cc_api_key === "****" ? "" : configData.cc_api_key;
    document.getElementById("cfg-base-url").value = configData.cc_base_url;
    document.getElementById("cfg-host").value = configData.host;
    document.getElementById("cfg-port").value = configData.port;
    document.getElementById("cfg-log-level").value = configData.log_level;
  } catch { showToast(t("saveFailed"), "error"); }
}

async function saveConfig() {
  const body = {};
  const key = document.getElementById("cfg-key").value;
  if (key) body.cc_api_key = key;
  const baseUrl = document.getElementById("cfg-base-url").value;
  if (baseUrl !== configData.cc_base_url) body.cc_base_url = baseUrl;
  const host = document.getElementById("cfg-host").value;
  if (host !== configData.host) body.host = host;
  const port = parseInt(document.getElementById("cfg-port").value);
  if (port !== configData.port) body.port = port;
  const logLevel = document.getElementById("cfg-log-level").value;
  if (logLevel !== configData.log_level) body.log_level = logLevel;
  if (Object.keys(body).length === 0) { showToast("No changes", "success"); return; }
  try {
    const resp = await api("PUT", "/admin/api/config", body);
    if (!resp.ok) throw new Error(await resp.text());
    configData = await resp.json();
    showToast(t("saved"), "success");
  } catch { showToast(t("saveFailed"), "error"); }
}

// Playground
async function renderPlayground() {
  const el = document.getElementById("tab-playground");
  el.innerHTML = `
    <h2 data-i18n="playground">${t("playground")}</h2>
    <div class="card playground-form" style="margin-top:16px">
      <div class="form-group">
        <label data-i18n="model">${t("model")}</label>
        <input type="text" id="pg-model" value="claude-sonnet-4-6" placeholder="claude-sonnet-4-6">
      </div>
      <div class="form-group">
        <label data-i18n="messages">${t("messages")}</label>
        <textarea id="pg-messages" placeholder='[{"role":"user","content":"Hello"}]'></textarea>
      </div>
      <div class="checkbox-row">
        <input type="checkbox" id="pg-stream" checked>
        <label for="pg-stream" data-i18n="stream">${t("stream")}</label>
      </div>
      <div class="form-actions">
        <button class="btn btn-primary" id="pg-send">${t("send")}</button>
        <button class="btn btn-secondary" id="pg-clear">${t("clear")}</button>
      </div>
    </div>
    <div class="response-area" id="pg-response"></div>`;
  document.getElementById("pg-send").onclick = sendPlayground;
  document.getElementById("pg-clear").onclick = () => {
    document.getElementById("pg-response").textContent = "";
  };
}

async function sendPlayground() {
  const model = document.getElementById("pg-model").value || "claude-sonnet-4-6";
  const messagesText = document.getElementById("pg-messages").value;
  const stream = document.getElementById("pg-stream").checked;
  let messages;
  try { messages = JSON.parse(messagesText); }
  catch { showToast("Invalid JSON in messages", "error"); return; }

  const respArea = document.getElementById("pg-response");
  respArea.textContent = "Sending...";

  if (stream) {
    const response = await fetch("/v1/chat/completions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model, messages, stream: true }),
    });
    if (!response.ok) {
      const err = await response.json();
      respArea.textContent = JSON.stringify(err, null, 2);
      return;
    }
    respArea.textContent = "";
    respArea.classList.add("streaming");
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        if (line.startsWith("data: ") && line !== "data: [DONE]") {
          try {
            const json = JSON.parse(line.slice(6));
            const content = json.choices?.[0]?.delta?.content || "";
            if (content) {
              const div = document.createElement("div");
              div.className = "line";
              div.textContent = content;
              respArea.appendChild(div);
              respArea.scrollTop = respArea.scrollHeight;
            }
          } catch {}
        }
      }
    }
    respArea.classList.remove("streaming");
  } else {
    try {
      const resp = await api("POST", "/v1/chat/completions", { model, messages, stream: false });
      const data = await resp.json();
      respArea.textContent = JSON.stringify(data, null, 2);
    } catch (e) {
      respArea.textContent = `Error: ${e.message}`;
    }
  }
}

// Init
document.addEventListener("DOMContentLoaded", () => {
  // Theme
  applyTheme();
  document.getElementById("theme-toggle").onclick = toggleTheme;

  // Lang
  document.getElementById("lang-switch").value = lang;
  document.getElementById("lang-switch").onchange = (e) => switchLang(e.target.value);

  // Login
  document.getElementById("login-btn").onclick = doLogin;
  document.getElementById("login-password").onkeydown = (e) => {
    if (e.key === "Enter") doLogin();
  };

  // Nav
  document.querySelectorAll(".nav-item").forEach(el => {
    el.onclick = () => switchTab(el.dataset.tab);
  });

  // Check auth on load
  (async () => {
    const resp = await fetch("/admin/api/health", {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (resp.status === 401) showLogin();
    else if (token) { renderAll(); }
    else { renderAll(); }
  })();
});
```

- [ ] **Step 2: Verify the page loads and works**

```bash
# Start the server
poetry run python -m cc_adapter
```
Then open http://localhost:8080/admin/ and verify:
- Page loads without JS errors
- Theme toggle works
- Lang switch works
- Dashboard shows status

- [ ] **Step 3: Commit**

```bash
git add cc_adapter/admin/static/admin.js
git commit -m "feat: add admin panel JavaScript with all tab logic"
```

---

### Task 8: Update .env.example

**Files:**
- Modify: `.env.example`

- [ ] **Step 1: Add admin_password**

```diff
 CC_API_KEY=user_your_key_here
 CC_BASE_URL=https://api.commandcode.ai
 CC_ADAPTER_HOST=0.0.0.0
 CC_ADAPTER_PORT=8080
 CC_ADAPTER_LOG_LEVEL=INFO
+CC_ADAPTER_ADMIN_PASSWORD=    # 管理面板密码，留空则不启用登录
```

- [ ] **Step 2: Commit**

```bash
git add .env.example
git commit -m "docs: add CC_ADAPTER_ADMIN_PASSWORD to .env.example"
```

---

### Task 9: Integration test and verify

- [ ] **Step 1: Run full test suite**

```bash
poetry run pytest tests/ -v
```
Expected: all tests pass (including existing translator + integration tests)

- [ ] **Step 2: Manual smoke test**

```bash
poetry run python -m cc_adapter &
sleep 2

# Test login
curl -s http://localhost:8080/admin/api/login -H "Content-Type: application/json" -d '{"password":""}'

# Test health
curl -s http://localhost:8080/admin/api/health

# Kill server
kill %1
```

- [ ] **Step 3: Final commit with any fixes**

```bash
git add -A
git commit -m "fix: address test and integration issues"
```
