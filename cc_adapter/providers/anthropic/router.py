from __future__ import annotations

import structlog

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from cc_adapter.providers.anthropic.models import AnthropicRequest
from cc_adapter.providers.anthropic.request import AnthropicTranslator
from cc_adapter.providers.anthropic.response import (
    translate_anthropic_stream,
    collect_and_translate_anthropic_nonstream,
)
from cc_adapter.command_code.client import CommandCodeClient
from cc_adapter.core.retry import retry_on_empty, stream_with_retry
from cc_adapter.core.runtime import get_config, get_anthropic_translator
from cc_adapter.core.constants import STREAMING_HEADERS
from cc_adapter.core.errors import AdapterError
from cc_adapter.core.utils import format_sse

logger = structlog.get_logger(__name__)

router = APIRouter()


def _get_client() -> CommandCodeClient:
    from cc_adapter.core.runtime import get_or_create_client

    return get_or_create_client()


def _anthropic_sse_error(message: str) -> str:
    return format_sse("error", {"type": "error", "error": {"type": "api_error", "message": message}})


@router.post("/v1/messages")
async def anthropic_chat(req: AnthropicRequest, request: Request):
    structlog.contextvars.bind_contextvars(protocol="anthropic")

    logger.info(
        "anthropic.request",
        model=req.model,
        stream=str(req.stream),
        message_count=len(req.messages),
        tools="yes" if req.tools else "no",
    )

    translator = get_anthropic_translator()
    cc_body, cc_headers = translator.translate(req)
    cc_body["params"]["stream"] = True

    current_client = _get_client()

    try:
        if req.stream:
            return StreamingResponse(
                stream_with_retry(
                    lambda: current_client.generate(cc_body, cc_headers),
                    lambda stream: translate_anthropic_stream(stream, req.model),
                    logger,
                    "anthropic.stream",
                    error_fn=lambda msg: _anthropic_sse_error(msg),
                ),
                media_type="text/event-stream",
                headers=STREAMING_HEADERS,
            )
        else:
            return await retry_on_empty(
                lambda: current_client.generate(cc_body, cc_headers),
                lambda stream: collect_and_translate_anthropic_nonstream(stream, req.model),
                logger,
                "anthropic.nonstream",
            )
    except AdapterError as e:
        return JSONResponse(
            status_code=e.status_code,
            content={"error": {"type": "api_error", "message": e.message}},
        )
