from __future__ import annotations

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from cc_adapter.core.errors import AdapterError
from cc_adapter.core.retry import retry_on_empty, stream_with_retry
from cc_adapter.core.runtime import get_config, get_or_create_client, get_responses_translator
from cc_adapter.core.constants import STREAMING_HEADERS
from cc_adapter.providers.openai.responses_models import ResponseCreateRequest
from cc_adapter.providers.openai.responses_response import (
    translate_responses_stream,
    collect_and_translate_responses_nonstream,
    _sse,
)

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.post("/v1/responses")
async def create_response(req: ResponseCreateRequest, request: Request):
    structlog.contextvars.bind_contextvars(protocol="responses")

    logger.info(
        "responses.request",
        model=req.model,
        stream=str(req.stream),
        input_type="string" if isinstance(req.input, str) else "list",
        tools="yes" if req.tools else "no",
    )

    try:
        translator = get_responses_translator()
        cc_body, _ = translator.translate(req)
        cc_body["params"]["stream"] = True

        current_client = get_or_create_client()

        client_headers = {k.lower(): v for k, v in request.headers.items()}

        if req.stream:
            return StreamingResponse(
                stream_with_retry(
                    lambda: current_client.generate(cc_body, client_headers),
                    lambda stream: translate_responses_stream(stream, req.model),
                    logger,
                    "responses.stream",
                    error_fn=lambda msg: _sse("error", {"code": 502, "message": msg}),
                ),
                media_type="text/event-stream",
                headers=STREAMING_HEADERS,
            )
        else:
            result = await retry_on_empty(
                lambda: current_client.generate(cc_body, client_headers),
                lambda stream: collect_and_translate_responses_nonstream(stream, req.model),
                logger,
                "responses.nonstream",
            )
            return result
    except AdapterError as e:
        return JSONResponse(
            status_code=e.status_code,
            content={"error": {"type": "api_error", "message": e.message}},
        )
