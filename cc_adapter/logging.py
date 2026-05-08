from __future__ import annotations

import logging
import time
from typing import Any

import structlog
from structlog.stdlib import ProcessorFormatter
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from uuid import uuid4


SENSITIVE_TOOL_FIELDS = {"oldString", "newString", "filePath", "old_str", "new_str", "path"}


def filter_sensitive_data(_logger: logging.Logger, _method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    for key in list(event_dict.keys()):
        if key in SENSITIVE_TOOL_FIELDS:
            event_dict[key] = "***"
        elif isinstance(event_dict[key], dict):
            _redact_sensitive_keys(event_dict[key])
    return event_dict


def _redact_sensitive_keys(d: dict[str, Any]) -> None:
    for k, v in list(d.items()):
        if k in SENSITIVE_TOOL_FIELDS:
            d[k] = "***"
        elif isinstance(v, dict):
            _redact_sensitive_keys(v)


def configure_logging(*, log_format: str, log_level: str | int) -> None:
    if isinstance(log_level, str):
        log_level = getattr(logging, log_level.upper(), logging.INFO)

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.dev.TimeStamper(fmt="iso"),
        filter_sensitive_data,
    ]

    if log_format == "json":
        formatter_processor: Any = structlog.processors.JSONRenderer()
    else:
        formatter_processor = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    handler = logging.StreamHandler()
    handler.setFormatter(
        ProcessorFormatter(
            foreign_pre_pend=False,
            processor=formatter_processor,
        )
    )

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-ID", uuid4().hex[:16])
        structlog.contextvars.bind_contextvars(request_id=request_id)

        start_time = time.time()
        response = await call_next(request)
        elapsed = time.time() - start_time

        logger = structlog.get_logger("cc_adapter.main")
        logger.info(
            "request_complete",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            elapsed=f"{elapsed:.3f}s",
        )

        response.headers["X-Request-ID"] = request_id
        return response
