from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any
from uuid import uuid4

import structlog
from structlog.stdlib import ProcessorFormatter
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint


SENSITIVE_KEYS = {
    "authorization",
    "x-api-key",
    "api_key",
    "token",
    "cookie",
    "set-cookie",
    "messages",
    "content",
    "oldstring",
    "newstring",
    "filepath",
    "old_str",
    "new_str",
}
SENSITIVE_KEYS_LOWER = {k.lower() for k in SENSITIVE_KEYS}


def _redact_sensitive_keys(d: dict[str, Any]) -> None:
    for k, v in list(d.items()):
        kl = k.lower()
        if kl in SENSITIVE_KEYS_LOWER:
            d[k] = "***"
        elif isinstance(v, dict):
            _redact_sensitive_keys(v)
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, dict):
                    _redact_sensitive_keys(item)


def filter_sensitive_data(_logger: logging.Logger, _method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    _redact_sensitive_keys(event_dict)
    return event_dict


_shared_processors: list[Any] = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_logger_name,
    structlog.stdlib.add_log_level,
    structlog.processors.TimeStamper(fmt="iso"),
    filter_sensitive_data,
]


class PrettyConsoleRenderer:
    _FIELD_PRIORITY = [
        "event",
        "req",
        "model",
        "method",
        "path",
        "status_code",
        "elapsed",
        "attempt",
        "error_type",
    ]

    _LEVEL_COLORS = {
        "critical": "\033[31m",
        "error": "\033[31m",
        "warning": "\033[33m",
        "warn": "\033[33m",
        "info": "\033[32m",
        "debug": "\033[36m",
    }
    _RESET = "\033[0m"
    _DIM = "\033[2m"
    _BOLD_CYAN = "\033[1;36m"

    def __call__(self, logger: logging.Logger, method_name: str, event_dict: dict[str, Any]) -> str:
        ts = event_dict.pop("timestamp", "")
        try:
            ts_parsed = datetime.fromisoformat(ts)
            ts_str = ts_parsed.strftime("%H:%M:%S")
        except (ValueError, TypeError):
            ts_str = ts

        level = event_dict.pop("level", "info")
        event = event_dict.pop("event", "")
        _ = event_dict.pop("logger", "")

        color = self._LEVEL_COLORS.get(level, "")
        level_upper = level.upper()

        # Map request_id → req if req not already set
        request_id = event_dict.pop("request_id", None)
        if request_id is not None and "req" not in event_dict:
            event_dict["req"] = request_id

        parts = [
            f"{self._DIM}{ts_str}{self._RESET}",
            f"{color}{level_upper:<5}{self._RESET}",
            f"  {self._BOLD_CYAN}{event:<16}{self._RESET}",
        ]

        for key in self._FIELD_PRIORITY:
            if key in event_dict:
                val = event_dict.pop(key)
                parts.append(f"{key}={val}")

        for key, val in list(event_dict.items()):
            parts.append(f"{key}={val}")

        return " ".join(parts)


def configure_logging(*, log_format: str, log_level: str | int) -> None:
    if isinstance(log_level, str):
        log_level = getattr(logging, log_level.upper(), logging.INFO)

    if log_format == "json":
        renderer: Any = structlog.processors.JSONRenderer()
    else:
        renderer = PrettyConsoleRenderer()

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *_shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = ProcessorFormatter(processor=renderer, foreign_pre_chain=_shared_processors)

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-ID", uuid4().hex[:16])
        structlog.contextvars.bind_contextvars(request_id=request_id)

        start_time = time.time()
        response = await call_next(request)
        elapsed = time.time() - start_time

        logger = structlog.get_logger("cc_adapter.main")
        logger.info(
            "http.done",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            elapsed=f"{elapsed:.3f}s",
        )

        response.headers["X-Request-ID"] = request_id
        return response
