from __future__ import annotations

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from cc_adapter.core.config import AppConfig
from cc_adapter.core.errors import AdapterError
from cc_adapter.core.auth import validate_token
from cc_adapter.core.runtime import get_config, get_client
from cc_adapter.providers.openai.responses_models import ResponseCreateRequest
from cc_adapter.providers.openai.responses_response import (
    translate_responses_stream,
    collect_and_translate_responses_nonstream,
    _sse,
)

logger = structlog.get_logger(__name__)

router = APIRouter()


def _get_responses_translator():
    from cc_adapter.providers.openai.responses_request import ResponsesRequestTranslator

    return ResponsesRequestTranslator()


async def _responses_stream_with_retry(generate_fn, model: str):
    for attempt in range(2):
        cc_stream = generate_fn()
        translator = translate_responses_stream(cc_stream, model)
        yielded_any = False
        try:
            async for chunk in translator:
                yielded_any = True
                yield chunk
        except AdapterError as e:
            logger.warning("responses.retry", reason="empty_response", attempt=attempt + 1, max_attempts=2)
            if not yielded_any and attempt == 0 and "empty response" in e.message.lower():
                continue
            yield _sse("error", {"code": 502, "message": e.message})
            return
        return


async def _responses_nonstream_with_retry(generate_fn, model: str):
    for attempt in range(2):
        cc_stream = generate_fn()
        try:
            return await collect_and_translate_responses_nonstream(cc_stream, model)
        except AdapterError as e:
            if attempt == 0 and "empty response" in e.message.lower():
                logger.warning("responses.nonstream.retry", reason="empty_response", attempt=1, max_attempts=2)
                continue
            raise


@router.post("/v1/responses")
async def create_response(req: ResponseCreateRequest, request: Request):
    structlog.contextvars.bind_contextvars(protocol="responses")
    cfg = get_config() or AppConfig()

    auth = request.headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else ""
    if cfg.access_key and token != cfg.access_key:
        if not (cfg.admin_password and validate_token(token)):
            return JSONResponse(
                status_code=401,
                content={"error": {"type": "authentication_error", "message": "Invalid API key"}},
            )

    logger.info(
        "responses.request",
        model=req.model,
        stream=str(req.stream),
        input_type="string" if isinstance(req.input, str) else "list",
        tools="yes" if req.tools else "no",
    )

    try:
        translator = _get_responses_translator()
        cc_body, cc_headers = translator.translate(req)
        cc_body["params"]["stream"] = True

        current_client = get_client()
        if current_client is None:
            from cc_adapter.command_code.client import CommandCodeClient

            current_client = CommandCodeClient(
                base_url=cfg.cc_base_url,
                api_key=cfg.cc_api_key[0] if cfg.cc_api_key else "",
                max_connections=cfg.http_max_connections,
                max_keepalive_connections=cfg.http_max_keepalive_connections,
                http2=cfg.http2,
            )
        if not current_client.api_key:
            return JSONResponse(
                status_code=401,
                content={
                    "error": {"type": "authentication_error", "message": "CC_ADAPTER_CC_API_KEY is not configured"}
                },
            )

        if req.stream:
            return StreamingResponse(
                _responses_stream_with_retry(
                    lambda: current_client.generate(cc_body, cc_headers),
                    req.model,
                ),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )
        else:
            result = await _responses_nonstream_with_retry(
                lambda: current_client.generate(cc_body, cc_headers),
                req.model,
            )
            return result
    except AdapterError as e:
        return JSONResponse(
            status_code=e.status_code,
            content={"error": {"type": "api_error", "message": e.message}},
        )
