from __future__ import annotations

import json
import time
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel

from cc_adapter.core.auth import generate_token, validate_token
from cc_adapter.core.runtime import get_config, get_client, init as state_init
from cc_adapter.core.config import AppConfig, DEFAULT_MODEL
from cc_adapter.command_code.client import CommandCodeClient
from cc_adapter.providers.shared.model_mapping import MODEL_PROVIDER_MAP, REASONING_EFFORT_MAX
from cc_adapter.command_code.body import make_cc_body, _make_config
from cc_adapter.admin.usage_client import query_all_tokens
from cc_adapter.command_code.headers import make_cc_headers
from cc_adapter.core.utils import normalize_api_keys, is_deepseek_v4_model

router = APIRouter(prefix="/admin/api")
logger = logging.getLogger(__name__)
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
    log_format: str | None = None
    default_model: str | None = None


def _primary_api_key(value: str | list[str] | None) -> str:
    from cc_adapter.core.utils import normalize_api_keys

    keys = normalize_api_keys(value)
    return keys[0] if keys else ""


_CONFIG_FIELDS = {"cc_api_key", "cc_base_url", "host", "port", "log_level", "log_format", "default_model"}
_CONFIG_CLIENT_FIELDS = {"cc_api_key", "cc_base_url"}


def _apply_config_fields(cfg: AppConfig, updates: dict[str, object]) -> bool:
    changed_client = False
    for field, value in updates.items():
        if field == "cc_api_key":
            value = normalize_api_keys(value)
        setattr(cfg, field, value)
        if field in _CONFIG_CLIENT_FIELDS:
            changed_client = True
    return changed_client


async def verify_auth(authorization: str | None = Header(None)):
    cfg = get_config()
    if not cfg or not cfg.admin_password:
        logger.warning("Admin auth blocked: CC_ADAPTER_ADMIN_PASSWORD is not configured")
        raise HTTPException(status_code=503, detail="Admin password is not configured")
    if not authorization or not authorization.startswith("Bearer "):
        logger.warning("Admin auth failed: missing or malformed Authorization header")
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = authorization[7:]
    if not validate_token(token):
        logger.warning("Admin auth failed: invalid token")
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True


@router.post("/login")
async def login(req: LoginRequest):
    cfg = get_config()
    if not cfg or not cfg.admin_password:
        raise HTTPException(status_code=503, detail="Admin password is not configured")
    if req.password != cfg.admin_password:
        logger.warning("Admin login failed: invalid password")
        raise HTTPException(status_code=401, detail="Invalid password")
    token = generate_token()
    return LoginResponse(token=token)


@router.get("/config")
async def get_config_endpoint(_=Depends(verify_auth)):
    cfg = get_config()
    return {
        "cc_api_key": f"{len(cfg.cc_api_key)} key(s) configured" if cfg and cfg.cc_api_key else "",
        "cc_base_url": cfg.cc_base_url if cfg else "",
        "host": cfg.host if cfg else "",
        "port": cfg.port if cfg else 8080,
        "log_level": cfg.log_level if cfg else "INFO",
        "log_format": cfg.log_format if cfg else "console",
        "admin_password_configured": bool(cfg and cfg.admin_password),
        "default_model": cfg.default_model if cfg else DEFAULT_MODEL,
    }


@router.get("/ui-config")
async def ui_config():
    cfg = get_config()
    return {
        "default_model": cfg.default_model if cfg else DEFAULT_MODEL,
    }


def _format_model_display_name(bare_name: str) -> str:
    for prefix, replacement in [
        ("deepseek-v4-", "DeepSeek V4 "),
        ("kimi-k2-", "Kimi K2 "),
        ("glm-", "GLM "),
        ("minimax-m2-", "Minimax M2 "),
        ("qwen-3-6-", "Qwen 3-6 "),
        ("step-3-5-", "Step 3-5 "),
    ]:
        if bare_name.startswith(prefix):
            suffix = bare_name[len(prefix) :]
            suffix = " ".join(word.capitalize() for word in suffix.split("-"))
            return replacement + suffix
    return bare_name.replace("-", " ").title()


@router.get("/models")
async def list_models():
    models = []
    for bare_name, canonical_id in MODEL_PROVIDER_MAP.items():
        display_name = _format_model_display_name(bare_name)
        provider = canonical_id.split("/")[0]
        models.append(
            {
                "id": canonical_id,
                "name": display_name,
                "provider": provider,
            }
        )
    return {"models": models}


@router.get("/reasoning-effort")
async def get_reasoning_effort_config(_=Depends(verify_auth)):
    return {
        "max_prompt": REASONING_EFFORT_MAX,
        "deepseek_v4_models": [k for k in MODEL_PROVIDER_MAP if k.startswith("deepseek-v4")],
        "description": (
            "For deepseek-v4 series models, when reasoning_effort is 'xhigh' or 'max', "
            "the REASONING_EFFORT_MAX prompt is prepended to the system prompt. "
            "'xhigh' is mapped to 'max'."
        ),
    }


@router.put("/config")
async def update_config(update: ConfigUpdate, _=Depends(verify_auth)):
    _update_env_file(update)
    await _apply_config_update(update)
    return await get_config_endpoint()


@router.get("/config/raw")
async def get_raw_config(_=Depends(verify_auth)):
    raise HTTPException(status_code=410, detail="Raw config editing is no longer available")


class RawConfigUpdate(BaseModel):
    content: str


@router.put("/config/raw")
async def update_raw_config(update: RawConfigUpdate, _=Depends(verify_auth)):
    raise HTTPException(status_code=410, detail="Raw config editing is no longer available")


@router.post("/verify-key")
async def verify_key(_=Depends(verify_auth)):
    cfg = get_config()
    if not cfg or not _primary_api_key(cfg.cc_api_key):
        return {"valid": False, "message": "No API Key configured"}
    test_client = CommandCodeClient(
        base_url=cfg.cc_base_url,
        api_key=_primary_api_key(cfg.cc_api_key),
        timeout=10.0,
        max_connections=cfg.http_max_connections,
        max_keepalive_connections=cfg.http_max_keepalive_connections,
        http2=cfg.http2,
    )
    try:
        test_body = make_cc_body(
            config=_make_config(
                {"workingDir": "/tmp", "structure": [], "isGitRepo": False, "date": "2026-01-01T00:00:00Z"}
            ),
            params={
                "model": cfg.default_model,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 10,
                "stream": True,
            },
        )
        headers = make_cc_headers()
        async for _ in test_client.generate(test_body, headers):
            break
        return {"valid": True, "message": "API Key is valid"}
    except Exception as e:
        return {"valid": False, "message": str(e)}
    finally:
        await test_client.aclose()


@router.post("/usage/query")
async def admin_usage_query(_=Depends(verify_auth)):
    cfg = get_config()
    if not cfg or not cfg.cc_api_key:
        return []
    results = await query_all_tokens(cfg.cc_base_url, cfg.cc_api_key)
    return results


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
        "cc_api_key": "CC_ADAPTER_CC_API_KEY",
        "cc_base_url": "CC_ADAPTER_CC_BASE_URL",
        "host": "CC_ADAPTER_HOST",
        "port": "CC_ADAPTER_PORT",
        "log_level": "CC_ADAPTER_LOG_LEVEL",
        "log_format": "CC_ADAPTER_LOG_FORMAT",
        "default_model": "CC_ADAPTER_DEFAULT_MODEL",
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
                value = (
                    normalize_api_keys(update_map[field_name]) if field_name == "cc_api_key" else update_map[field_name]
                )
                if field_name == "cc_api_key":
                    lines[i] = f"{env_key}={json.dumps(value)}\n"
                else:
                    lines[i] = f"{env_key}={value}\n"
                existing_keys.add(field_name)
    for field_name, env_key in field_map.items():
        if field_name in update_map and field_name not in existing_keys:
            value = normalize_api_keys(update_map[field_name]) if field_name == "cc_api_key" else update_map[field_name]
            if field_name == "cc_api_key":
                lines.append(f"{env_key}={json.dumps(value)}\n")
            else:
                lines.append(f"{env_key}={update_map[field_name]}\n")
    env_path.write_text("".join(lines))


def _recreate_client(cfg: AppConfig) -> CommandCodeClient | None:
    old = get_client()
    state_init(
        cfg,
        CommandCodeClient(
            base_url=cfg.cc_base_url,
            api_key=_primary_api_key(cfg.cc_api_key),
            max_connections=cfg.http_max_connections,
            max_keepalive_connections=cfg.http_max_keepalive_connections,
            http2=cfg.http2,
        ),
    )
    return old


async def _apply_config_update(update: ConfigUpdate) -> None:
    update_dict = update.model_dump(exclude_none=True)
    cfg = get_config()
    if cfg is None:
        return
    changed_client = _apply_config_fields(cfg, update_dict)
    if changed_client:
        old = _recreate_client(cfg)
        if old is not None:
            await old.aclose()
