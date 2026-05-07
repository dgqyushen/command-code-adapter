from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

_admin_password: str = ""
_TOKEN_TTL: int = 86400


def set_password(password: str) -> None:
    global _admin_password
    _admin_password = password


def _password_hash() -> str:
    return hashlib.sha256(_admin_password.encode()).hexdigest()[:16]


def _sign(payload: str) -> str:
    return hmac.new(
        _admin_password.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()


def generate_token() -> str:
    exp = int(time.time()) + _TOKEN_TTL
    payload = base64.urlsafe_b64encode(
        json.dumps({"exp": exp, "pwh": _password_hash()}).encode()
    ).decode()
    sig = _sign(payload)
    return f"{payload}.{sig}"


def validate_token(token: str) -> bool:
    if not _admin_password:
        return True
    try:
        payload_b64, sig = token.split(".", 1)
        if not hmac.compare_digest(_sign(payload_b64), sig):
            return False
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        if time.time() > payload["exp"]:
            return False
        if payload.get("pwh") != _password_hash():
            return False
        return True
    except Exception:
        return False
