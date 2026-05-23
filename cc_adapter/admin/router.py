from __future__ import annotations

import structlog
import time
from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel

from cc_adapter.core.auth import generate_token, validate_token
from cc_adapter.core.runtime import (
    get_config,
    get_provider_map,
    get_reasoning_efforts,
    get_model_fetcher,
)
from cc_adapter.core.config import DEFAULT_MODEL
from cc_adapter.core.constants import VERSION
from cc_adapter.command_code.body import make_cc_body, make_config
from cc_adapter.admin.config_manager import ConfigManager
from cc_adapter.admin.usage_client import query_all_tokens, query_daily_usage
from cc_adapter.command_code.headers import make_cc_headers
from cc_adapter.core.utils import normalize_api_keys
from cc_adapter.core import log_buffer

router = APIRouter(prefix="/admin/api")
logger = structlog.get_logger(__name__)
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


async def verify_auth(authorization: str | None = Header(None)):
    cfg = get_config()
    if not cfg or not cfg.admin_password:
        logger.warning("auth.failed", reason="admin_password_not_configured")
        raise HTTPException(status_code=503, detail="Admin password is not configured")
    if not authorization or not authorization.startswith("Bearer "):
        logger.warning("auth.failed", reason="missing_or_malformed_auth_header")
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = authorization[7:]
    if not validate_token(token):
        logger.warning("auth.failed", reason="invalid_admin_token")
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True


@router.post("/login")
async def login(req: LoginRequest):
    cfg = get_config()
    if not cfg or not cfg.admin_password:
        raise HTTPException(status_code=503, detail="Admin password is not configured")
    if req.password != cfg.admin_password:
        logger.warning("admin.login.failed", reason="invalid_password")
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


_MODEL_DISPLAY_PREFIXES: dict[str, str] = {
    "deepseek-v4-": "DeepSeek V4 ",
    "kimi-k2-": "Kimi K2 ",
    "glm-": "GLM ",
    "minimax-m2-": "Minimax M2 ",
    "qwen-3-6-": "Qwen 3-6 ",
    "step-3-5-": "Step 3-5 ",
}


def _format_model_display_name(bare_name: str) -> str:
    for prefix, replacement in _MODEL_DISPLAY_PREFIXES.items():
        if bare_name.startswith(prefix):
            suffix = bare_name[len(prefix) :]
            suffix = " ".join(word.capitalize() for word in suffix.split("-"))
            return replacement + suffix
    return bare_name.replace("-", " ").title()


@router.get("/models")
async def list_models():
    models = []
    for bare_name, canonical_id in get_provider_map().items():
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
async def get_reasoning_effort_config():
    return {
        "model_reasoning_efforts": get_reasoning_efforts(),
        "description": (
            "Per-model supported reasoning_effort levels. "
            "Values not in the list are clamped to the nearest higher level."
        ),
    }


@router.get("/models/status")
async def models_status():
    return get_model_fetcher().get_status()


@router.put("/config")
async def update_config(update: ConfigUpdate, _=Depends(verify_auth)):
    update_dict = update.model_dump(exclude_none=True)
    ConfigManager.update_env_file(update_dict)
    await ConfigManager.apply_config_update(update_dict)
    return await get_config_endpoint()


@router.post("/verify-key")
async def verify_key(_=Depends(verify_auth)):
    cfg = get_config()
    keys = normalize_api_keys(cfg.cc_api_key) if cfg else []
    primary_key = keys[0] if keys else ""
    if not cfg or not primary_key:
        result = {"valid": False, "message": "No API Key configured"}
        logger.info("admin.verify_key", valid=result["valid"])
        return result
    from cc_adapter.core.runtime import create_client

    test_client = create_client(cfg, timeout=10.0)
    try:
        test_body = make_cc_body(
            config=make_config(
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
        result = {"valid": True, "message": "API Key is valid"}
    except Exception as e:
        result = {"valid": False, "message": str(e)}
    finally:
        await test_client.aclose()
    logger.info("admin.verify_key", valid=result["valid"])
    return result


@router.post("/usage/query")
async def admin_usage_query(_=Depends(verify_auth)):
    cfg = get_config()
    if not cfg or not cfg.cc_api_key:
        return []
    results = await query_all_tokens(cfg.cc_base_url, cfg.cc_api_key)
    return results


class DailyUsageRequest(BaseModel):
    start_date: str
    end_date: str


@router.post("/usage/daily")
async def admin_daily_usage(req: DailyUsageRequest, _=Depends(verify_auth)):
    cfg = get_config()
    if not cfg or not cfg.cc_api_key:
        return {"daily": [], "totals": {"total_cost": 0, "total_count": 0, "models": []}}
    primary_key = normalize_api_keys(cfg.cc_api_key)
    if not primary_key:
        return {"daily": [], "totals": {"total_cost": 0, "total_count": 0, "models": []}}
    start = date_type.fromisoformat(req.start_date)
    end = date_type.fromisoformat(req.end_date)
    daily = await query_daily_usage(cfg.cc_base_url, primary_key[0], start, end)

    total_cost = sum(d["total_cost"] for d in daily)
    total_count = sum(d["total_count"] for d in daily)

    model_agg: dict[str, dict[str, object]] = {}
    for d in daily:
        for m in d.get("models", []):
            mid = m["model_id"]
            if mid not in model_agg:
                model_agg[mid] = {"model_id": mid, "cost": 0.0, "count": 0}
            model_agg[mid]["cost"] += m["cost"]
            model_agg[mid]["count"] += m["count"]

    models_list = sorted(model_agg.values(), key=lambda x: x["cost"], reverse=True)
    for m in models_list:
        m["pct"] = round((m["cost"] / total_cost * 100), 1) if total_cost > 0 else 0

    return {
        "daily": daily,
        "totals": {
            "total_cost": round(total_cost, 4),
            "total_count": total_count,
            "models": models_list,
        },
    }


@router.get("/health")
async def admin_health(_=Depends(verify_auth)):
    cfg = get_config()
    return {
        "status": "ok",
        "version": VERSION,
        "uptime": int(time.time() - _start_time),
        "cc_api_key_configured": bool(cfg and cfg.cc_api_key),
    }


@router.get("/logs")
async def get_logs(level: str = "INFO", search: str = "", limit: int = 200, _=Depends(verify_auth)):
    if limit < 1:
        limit = 200
    if limit > 500:
        limit = 500
    entries = log_buffer.get_entries(level=level, search=search, limit=limit)
    entries = [e for e in entries if e.get("path") != "/admin/api/logs"]
    return {"entries": entries, "total_in_buffer": log_buffer.buffer_size()}
