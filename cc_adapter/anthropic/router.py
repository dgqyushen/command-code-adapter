from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from cc_adapter.anthropic.models import AnthropicRequest
from cc_adapter.anthropic.request import AnthropicTranslator
from cc_adapter.anthropic.response import (
    translate_anthropic_stream,
    collect_and_translate_anthropic_nonstream,
)
from cc_adapter.admin.state import get_client as get_admin_client, get_config as get_admin_config
from cc_adapter.config import AppConfig
from cc_adapter.client import CommandCodeClient
from cc_adapter.errors import AdapterError

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_client() -> CommandCodeClient:
    cfg = get_admin_config() or AppConfig()
    api_key = cfg.cc_api_key[0] if cfg.cc_api_key else ""
    return get_admin_client() or CommandCodeClient(base_url=cfg.cc_base_url, api_key=api_key)


async def _anthropic_stream_with_retry(
    client: CommandCodeClient,
    body: dict,
    headers: dict,
    model: str,
):
    for attempt in range(2):
        cc_stream = client.generate(body, headers)
        translator = translate_anthropic_stream(cc_stream, model)
        should_retry = False
        async for chunk in translator:
            should_retry = True
            yield chunk
        if not should_retry and attempt == 0:
            logger.warning("Empty upstream response in anthropic stream (attempt 1/2), retrying...")
            continue
        return


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
    cfg = get_admin_config() or AppConfig()

    api_key_header = request.headers.get("x-api-key", "")
    auth = request.headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else api_key_header

    if cfg.access_key and token != cfg.access_key:
        from cc_adapter.admin.auth import validate_token

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

    cc_body, cc_headers = AnthropicTranslator().translate(req)
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
