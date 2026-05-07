from __future__ import annotations

import json
import os
import time
import re
import logging
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel

from cc_adapter.admin.auth import generate_token, validate_token
from cc_adapter.admin.state import get_config, get_client, init as state_init
from cc_adapter.config import AppConfig, DEFAULT_MODEL
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
    default_model: str | None = None


def _normalize_api_keys(value: str | list[str] | None) -> list[str]:
    if isinstance(value, list):
        return [key for key in value if key]
    if isinstance(value, str):
        if not value:
            return []
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [key for key in parsed if key]
        except (json.JSONDecodeError, TypeError):
            pass
        return [value]
    return []


def _primary_api_key(value: str | list[str] | None) -> str:
    keys = _normalize_api_keys(value)
    return keys[0] if keys else ""


async def verify_auth(authorization: str | None = Header(None)):
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
        "default_model": cfg.default_model if cfg else DEFAULT_MODEL,
    }


@router.get("/ui-config")
async def ui_config():
    cfg = get_config()
    return {
        "default_model": cfg.default_model if cfg else DEFAULT_MODEL,
    }


@router.put("/config")
async def update_config(update: ConfigUpdate, _=Depends(verify_auth)):
    _update_env_file(update)
    _apply_config_update(update)
    return await get_config_endpoint()


@router.get("/config/raw")
async def get_raw_config(_=Depends(verify_auth)):
    env_path = Path(".env")
    content = env_path.read_text() if env_path.exists() else ""
    return {"content": content}


class RawConfigUpdate(BaseModel):
    content: str


@router.put("/config/raw")
async def update_raw_config(update: RawConfigUpdate, _=Depends(verify_auth)):
    env_path = Path(".env")
    env_path.write_text(update.content)

    cfg = get_config()
    if cfg:
        new_cfg = AppConfig(_env_file=".env")
        cfg.cc_api_key = new_cfg.cc_api_key
        cfg.cc_base_url = new_cfg.cc_base_url
        cfg.host = new_cfg.host
        cfg.port = new_cfg.port
        cfg.log_level = new_cfg.log_level
        cfg.default_model = new_cfg.default_model

        from cc_adapter.admin.state import init
        new_client = CommandCodeClient(base_url=cfg.cc_base_url, api_key=_primary_api_key(cfg.cc_api_key))
        init(cfg, new_client)

    return {"content": update.content}


@router.post("/verify-key")
async def verify_key(_=Depends(verify_auth)):
    cfg = get_config()
    if not cfg or not _primary_api_key(cfg.cc_api_key):
        return {"valid": False, "message": "No API Key configured"}
    test_client = CommandCodeClient(base_url=cfg.cc_base_url, api_key=_primary_api_key(cfg.cc_api_key), timeout=10.0)
    try:
        test_body = {
            "config": {"env": "adapter", "workingDir": "/tmp", "date": "2026-01-01T00:00:00Z", "environment": "production", "structure": [], "isGitRepo": False, "currentBranch": "main", "mainBranch": "main", "gitStatus": "clean", "recentCommits": []},
            "memory": "",
            "taste": None,
            "skills": None,
            "permissionMode": "standard",
            "params": {"model": cfg.default_model, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 10, "stream": False},
        }
        headers = {
            "x-command-code-version": "0.25.2-adapter",
            "x-cli-environment": "production",
            "x-project-slug": "adapter",
            "x-internal-team-flag": "false",
            "x-taste-learning": "false",
        }
        async for _ in test_client.generate(test_body, headers):
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
        cfg.cc_api_key = _normalize_api_keys(update_dict["cc_api_key"])
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
    if "default_model" in update_dict:
        cfg.default_model = update_dict["default_model"]

    if changed_client:
        new_client = CommandCodeClient(base_url=cfg.cc_base_url, api_key=_primary_api_key(cfg.cc_api_key))
        init(cfg, new_client)
