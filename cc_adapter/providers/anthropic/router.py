from __future__ import annotations

import httpx
import structlog
from typing import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from cc_adapter.providers.anthropic.models import (
    AnthropicRequest,
    AnthropicResponse,
    AnthropicUsage,
    extract_system_text,
    normalize_system_messages,
)
from cc_adapter.providers.anthropic.response import (
    translate_anthropic_stream,
    collect_and_translate_anthropic_nonstream,
)
from cc_adapter.command_code.client import CommandCodeClient
from cc_adapter.core.retry import retry_on_empty, stream_with_retry
from cc_adapter.core.runtime import get_config, get_anthropic_translator
from cc_adapter.core.constants import STREAMING_HEADERS
from cc_adapter.core.errors import AdapterError
from cc_adapter.core.utils import format_sse, generate_id

logger = structlog.get_logger(__name__)

router = APIRouter()


def _get_client() -> CommandCodeClient:
    from cc_adapter.core.runtime import get_or_create_client

    return get_or_create_client()


def _anthropic_sse_error(message: str) -> str:
    return format_sse("error", {"type": "error", "error": {"type": "api_error", "message": message}})


def _build_deepseek_body(req: AnthropicRequest) -> dict:
    config = get_config()
    model_override = config.web_search_model.strip() if config and config.web_search_model else ""
    model = model_override or req.model
    body: dict = {
        "model": model,
        "max_tokens": req.max_tokens,
        "stream": req.stream,
        "messages": [m.model_dump(exclude_none=True) for m in req.messages],
    }

    system_text = extract_system_text(req.system)
    if system_text:
        body["system"] = system_text

    if req.tools:
        body["tools"] = [t.model_dump(exclude_none=True) for t in req.tools]
    if req.tool_choice:
        body["tool_choice"] = req.tool_choice.model_dump(exclude_none=True)

    if req.thinking and req.thinking.type in ("enabled", "adaptive"):
        thinking_config: dict = {"type": req.thinking.type}
        if req.thinking.budget_tokens is not None:
            thinking_config["budget_tokens"] = req.thinking.budget_tokens
        body["thinking"] = thinking_config

    if req.temperature is not None:
        body["temperature"] = req.temperature

    for field in ("top_p", "top_k", "stop_sequences", "metadata"):
        value = getattr(req, field, None)
        if value is not None:
            body[field] = value

    if req.model_extra:
        for field, value in req.model_extra.items():
            if value is not None and field not in body:
                body[field] = value

    return body


async def _stream_from_deepseek(req: AnthropicRequest) -> AsyncGenerator[str, None]:
    config = get_config()
    url = f"{config.deepseek_anthropic_url}/v1/messages"
    headers = {
        "x-api-key": config.deepseek_api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }

    body = _build_deepseek_body(req)
    body["stream"] = True

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", url, json=body, headers=headers) as resp:
                if resp.status_code != 200:
                    error_text = await resp.aread()
                    error_str = str(error_text)
                    logger.warning("deepseek.forward.error", status_code=resp.status_code, error=error_str)
                    yield _anthropic_sse_error(f"DeepSeek API error {resp.status_code}")
                    return
                async for line in resp.aiter_lines():
                    yield line + "\n"
    except httpx.RequestError as e:
        logger.warning("deepseek.forward.request_error", error=str(e))
        yield _anthropic_sse_error(f"DeepSeek API connection error: {e}")
    except Exception as e:
        logger.warning("deepseek.forward.unexpected_error", error=str(e))
        yield _anthropic_sse_error(str(e))


async def _deepseek_nonstream(req: AnthropicRequest) -> AnthropicResponse:
    config = get_config()
    url = f"{config.deepseek_anthropic_url}/v1/messages"
    headers = {
        "x-api-key": config.deepseek_api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }

    body = _build_deepseek_body(req)
    body["stream"] = False

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, json=body, headers=headers)
            if resp.status_code != 200:
                logger.warning("deepseek.forward.nonstream_error", status_code=resp.status_code, error=resp.text)
                raise AdapterError(message=f"DeepSeek API returned {resp.status_code}", status_code=502)
            data = resp.json()

        usage = data.get("usage", {})

        return AnthropicResponse(
            id=data.get("id", generate_id("msg_", 16)),
            content=data.get("content", []),
            model=data.get("model", req.model),
            stop_reason=data.get("stop_reason"),
            usage=AnthropicUsage(
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
            ),
        )
    except httpx.RequestError as e:
        logger.warning("deepseek.forward.nonstream_request_error", error=str(e))
        raise AdapterError(message=f"DeepSeek API connection error: {e}", status_code=502)


@router.post("/v1/messages")
async def anthropic_chat(req: AnthropicRequest, request: Request):
    structlog.contextvars.bind_contextvars(protocol="anthropic")
    req = normalize_system_messages(req)

    logger.info(
        "anthropic.request",
        model=req.model,
        stream=str(req.stream),
        message_count=len(req.messages),
        tools="yes" if req.tools else "no",
    )

    from cc_adapter.providers.shared.web_search import has_anthropic_web_search_tool, is_web_search_enabled

    config = get_config()

    if is_web_search_enabled(config) and has_anthropic_web_search_tool(req.tools):
        logger.info("anthropic.web_search.forward", model=req.model)
        try:
            if req.stream:
                return StreamingResponse(
                    _stream_from_deepseek(req),
                    media_type="text/event-stream",
                    headers=STREAMING_HEADERS,
                )
            return await _deepseek_nonstream(req)
        except AdapterError as e:
            return JSONResponse(
                status_code=e.status_code,
                content={"error": {"type": "api_error", "message": e.message}},
            )

    try:
        translator = get_anthropic_translator()
        cc_body, _ = translator.translate(req)
        cc_body["params"]["stream"] = True

        current_client = _get_client()

        client_headers = {k.lower(): v for k, v in request.headers.items()}

        if req.stream:
            return StreamingResponse(
                stream_with_retry(
                    lambda: current_client.generate(cc_body, client_headers),
                    lambda stream: translate_anthropic_stream(stream, req.model),
                    logger,
                    "anthropic.stream",
                    error_fn=lambda msg: _anthropic_sse_error(msg),
                ),
                media_type="text/event-stream",
                headers=STREAMING_HEADERS,
            )
        return await retry_on_empty(
            lambda: current_client.generate(cc_body, client_headers),
            lambda stream: collect_and_translate_anthropic_nonstream(stream, req.model),
            logger,
            "anthropic.nonstream",
        )
    except AdapterError as e:
        return JSONResponse(
            status_code=e.status_code,
            content={"error": {"type": "api_error", "message": e.message}},
        )
