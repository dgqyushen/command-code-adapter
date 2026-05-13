from __future__ import annotations

import json
import time

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from cc_adapter.core.config import AppConfig
from cc_adapter.core.errors import AdapterError, AuthenticationError
from cc_adapter.core.auth import validate_token
from cc_adapter.core.runtime import get_config, get_client, get_request_translator
from cc_adapter.providers.openai.models import ChatCompletionRequest
from cc_adapter.providers.openai.response import translate_stream, collect_and_translate_nonstream

logger = structlog.get_logger(__name__)

router = APIRouter()


def _chunk_payload(chunk: str) -> dict | None:
    try:
        payload = chunk.removeprefix("data: ").strip()
        if payload == "[DONE]":
            return None
        data = json.loads(payload)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _is_empty_error(data: dict | None) -> bool:
    return bool(data and data.get("error", {}).get("message") == "Upstream model returned an empty response")


def _has_visible_delta(data: dict | None) -> bool:
    if not data:
        return False
    for choice in data.get("choices", []):
        delta = choice.get("delta") or {}
        if delta.get("content") or delta.get("tool_calls"):
            return True
    return False


def _has_streamable_delta(data: dict | None) -> bool:
    if not data:
        return False
    for choice in data.get("choices", []):
        delta = choice.get("delta") or {}
        if delta.get("content") or delta.get("reasoning_content") or delta.get("tool_calls"):
            return True
    return False


def _log_stream_metrics(
    model: str, empty_retry_count: int, retry_latencies: list[float], first_token_latency: float | None
):
    if empty_retry_count:
        logger.info(
            "Stream metric: model=%s empty_retry_count=%d retry_latencies=%s first_token_latency=%.3fs",
            model,
            empty_retry_count,
            [f"{t:.3f}s" for t in retry_latencies],
            first_token_latency or 0.0,
        )


async def _stream_with_retry(
    generate_fn,
    model: str,
    start_time: float,
    reasoning_effort: str | None = None,
    tools_available: bool = False,
):
    empty_retry_count = 0
    retry_latencies: list[float] = []
    first_token_latency: float | None = None

    for attempt in range(2):
        cc_stream = generate_fn()
        translator = translate_stream(cc_stream, model, start_time, reasoning_effort, tools_available)
        buffer_until_visible = attempt == 0 and tools_available
        buffered_chunks: list[str] = []
        flushed_chunks = False
        should_retry = False
        emitted_visible_delta = False

        async for chunk in translator:
            data = _chunk_payload(chunk)
            if _has_visible_delta(data):
                emitted_visible_delta = True
                if first_token_latency is None:
                    first_token_latency = time.time() - start_time

            if attempt == 0 and not emitted_visible_delta and _is_empty_error(data):
                logger.warning("Empty upstream response (attempt 1/2), retrying...")
                await translator.aclose()
                should_retry = True
                break

            if buffer_until_visible:
                buffered_chunks.append(chunk)
                if _has_streamable_delta(data):
                    for buffered_chunk in buffered_chunks:
                        yield buffered_chunk
                        flushed_chunks = True
                    buffered_chunks.clear()
                    buffer_until_visible = False
                continue

            yield chunk
            flushed_chunks = True
        else:
            for buffered_chunk in buffered_chunks:
                yield buffered_chunk
                flushed_chunks = True
            _log_stream_metrics(model, empty_retry_count, retry_latencies, first_token_latency)
            return

        if should_retry:
            empty_retry_count += 1
            retry_latencies.append(time.time() - start_time)
            continue

    _log_stream_metrics(model, empty_retry_count, retry_latencies, first_token_latency)


async def _nonstream_with_retry(
    generate_fn,
    model: str,
    start_time: float,
    reasoning_effort: str | None = None,
    tools_available: bool = False,
):
    for attempt in range(2):
        cc_stream = generate_fn()
        try:
            return await collect_and_translate_nonstream(
                cc_stream, model, start_time, reasoning_effort, tools_available
            )
        except AdapterError as e:
            if attempt == 0 and "empty response" in e.message.lower():
                logger.warning("Empty upstream response (attempt 1/2), retrying...")
                continue
            raise


@router.post("/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest, request: Request):
    structlog.contextvars.bind_contextvars(protocol="openai")
    cfg = get_config()
    if cfg and cfg.access_key:
        auth = request.headers.get("Authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else ""
        if token != cfg.access_key:
            if cfg.admin_password and validate_token(token):
                pass
            else:
                logger.warning("auth.failed", reason="invalid_access_key")
                return JSONResponse(
                    status_code=401,
                    content={
                        "error": {
                            "message": "Invalid API key",
                            "type": "invalid_request_error",
                            "code": "invalid_api_key",
                        }
                    },
                )

    if cfg is None:
        cfg = AppConfig()

    logger.info(
        "openai.request",
        model=req.model,
        stream=str(req.stream),
        message_count=len(req.messages),
        tools="yes" if req.tools else "no",
        tool_choice=req.tool_choice,
    )

    translator = get_request_translator()
    if translator is None:
        raise AuthenticationError("Request translator not initialized")
    cc_body, cc_headers = translator.translate(req)
    cc_body["params"]["stream"] = True
    tools_available = bool(req.tools) and req.tool_choice != "none"

    start_time = time.time()

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
        raise AuthenticationError("CC_ADAPTER_CC_API_KEY is not configured")

    if req.stream:
        return StreamingResponse(
            _stream_with_retry(
                lambda: current_client.generate(cc_body, cc_headers),
                req.model,
                start_time,
                req.reasoning_effort,
                tools_available,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    else:
        return await _nonstream_with_retry(
            lambda: current_client.generate(cc_body, cc_headers),
            req.model,
            start_time,
            req.reasoning_effort,
            tools_available,
        )
