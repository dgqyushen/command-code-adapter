from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from cc_adapter.providers.anthropic.models import AnthropicRequest
from cc_adapter.providers.anthropic.request import AnthropicTranslator
from cc_adapter.providers.anthropic.response import (
    translate_anthropic_stream,
    collect_and_translate_anthropic_nonstream,
)
from cc_adapter.core.runtime import get_client, get_config, get_anthropic_translator
from cc_adapter.core.config import AppConfig
from cc_adapter.command_code.client import CommandCodeClient
from cc_adapter.core.errors import AdapterError

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_client() -> CommandCodeClient:
    cfg = get_config() or AppConfig()
    api_key = cfg.cc_api_key[0] if cfg.cc_api_key else ""
    existing = get_client()
    if existing is not None:
        return existing
    return CommandCodeClient(
        base_url=cfg.cc_base_url,
        api_key=api_key,
        max_connections=cfg.http_max_connections,
        max_keepalive_connections=cfg.http_max_keepalive_connections,
        http2=cfg.http2,
    )


async def _anthropic_stream_with_retry(
    client: CommandCodeClient,
    body: dict,
    headers: dict,
    model: str,
):
    for attempt in range(2):
        cc_stream = client.generate(body, headers)
        translator = translate_anthropic_stream(cc_stream, model)
        yielded_any = False
        try:
            async for chunk in translator:
                yielded_any = True
                yield chunk
        except AdapterError as e:
            logger.warning("Anthropic stream AdapterError: %s (attempt %d/2)", e.message, attempt + 1)
            if not yielded_any and attempt == 0 and "empty response" in e.message.lower():
                continue
            yield _anthropic_sse_error(e.message)
            return
        return


def _anthropic_sse_error(message: str) -> str:
    data = json.dumps(
        {"type": "error", "error": {"type": "api_error", "message": message}},
        ensure_ascii=False,
    )
    return f"event: error\ndata: {data}\n\n"


async def _anthropic_nonstream_with_retry(
    client: CommandCodeClient,
    body: dict,
    headers: dict,
    model: str,
):
    for attempt in range(2):
        cc_stream = client.generate(body, headers)
        try:
            return await collect_and_translate_anthropic_nonstream(cc_stream, model)
        except AdapterError as e:
            if attempt == 0 and "empty response" in e.message.lower():
                logger.warning("Empty upstream response in anthropic nonstream (attempt 1/2), retrying...")
                continue
            raise


@router.post("/v1/messages")
async def anthropic_chat(req: AnthropicRequest, request: Request):
    cfg = get_config() or AppConfig()

    api_key_header = request.headers.get("x-api-key", "")
    auth = request.headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else api_key_header

    if cfg.access_key and token != cfg.access_key:
        from cc_adapter.core.auth import validate_token

        if not (cfg.admin_password and validate_token(token)):
            return JSONResponse(
                status_code=401,
                content={"error": {"type": "authentication_error", "message": "Invalid API key"}},
            )

    logger.info(
        "Anthropic request: model=%s stream=%s messages=%d tools=%s",
        req.model,
        req.stream,
        len(req.messages),
        "yes" if req.tools else "no",
    )

    translator = get_anthropic_translator()
    cc_body, cc_headers = translator.translate(req)
    cc_body["params"]["stream"] = True

    current_client = _get_client()
    if not current_client.api_key:
        return JSONResponse(
            status_code=401,
            content={"error": {"type": "authentication_error", "message": "CC_ADAPTER_CC_API_KEY is not configured"}},
        )

    try:
        if req.stream:
            return StreamingResponse(
                _anthropic_stream_with_retry(current_client, cc_body, cc_headers, req.model),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )
        else:
            return await _anthropic_nonstream_with_retry(current_client, cc_body, cc_headers, req.model)
    except AdapterError as e:
        return JSONResponse(
            status_code=e.status_code,
            content={"error": {"type": "api_error", "message": e.message}},
        )
