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
