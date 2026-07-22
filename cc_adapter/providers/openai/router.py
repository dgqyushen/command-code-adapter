from __future__ import annotations

import time

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from cc_adapter.core.retry import retry_on_empty, stream_with_retry, _BufferDetector
from cc_adapter.core.runtime import get_request_translator, get_or_create_client
from cc_adapter.core.constants import STREAMING_HEADERS
from cc_adapter.providers.openai.models import ChatCompletionRequest
from cc_adapter.providers.openai.response import translate_stream, collect_and_translate_nonstream

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.post("/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest, request: Request):
    structlog.contextvars.bind_contextvars(protocol="openai")

    logger.info(
        "openai.request",
        model=req.model,
        stream=str(req.stream),
        message_count=len(req.messages),
        tools="yes" if req.tools else "no",
        tool_choice=req.tool_choice,
    )

    translator = get_request_translator()
    cc_body, _ = translator.translate(req)
    cc_body["params"]["stream"] = True
    tools_available = bool(req.tools) and req.tool_choice != "none"

    start_time = time.time()

    # Forward client-authored session headers so the upstream session id can
    # be derived from them when present (e.g. X-Session-ID).
    client_headers = {k.lower(): v for k, v in request.headers.items()}
    current_client = get_or_create_client()

    if req.stream:
        detector = _BufferDetector() if tools_available else None
        return StreamingResponse(
            stream_with_retry(
                lambda: current_client.generate(cc_body, client_headers),
                lambda stream: translate_stream(stream, req.model, start_time, req.reasoning_effort, tools_available),
                logger,
                "openai.stream",
                buffer_detector=detector,
            ),
            media_type="text/event-stream",
            headers=STREAMING_HEADERS,
        )
    else:
        return await retry_on_empty(
            lambda: current_client.generate(cc_body, client_headers),
            lambda stream: collect_and_translate_nonstream(
                stream, req.model, start_time, req.reasoning_effort, tools_available
            ),
            logger,
            "openai.nonstream",
        )
