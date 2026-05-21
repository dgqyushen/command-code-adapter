from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse


def extract_token(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return request.headers.get("x-api-key", "")


def auth_error_response(protocol: str = "openai") -> JSONResponse:
    if protocol == "anthropic":
        body = {"error": {"type": "authentication_error", "message": "Invalid API key"}}
    else:
        body = {
            "error": {
                "message": "Invalid API key",
                "type": "invalid_request_error",
                "code": "invalid_api_key",
            }
        }
    return JSONResponse(status_code=401, content=body)


def missing_key_response(protocol: str = "openai") -> JSONResponse:
    body = {"error": {"type": "authentication_error", "message": "CC_ADAPTER_CC_API_KEY is not configured"}}
    return JSONResponse(status_code=401, content=body)
