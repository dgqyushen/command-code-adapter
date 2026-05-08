from __future__ import annotations

import json
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from cc_adapter.config import AppConfig
from cc_adapter.client import CommandCodeClient
from cc_adapter.logging import configure_logging, CorrelationIDMiddleware
from cc_adapter.translator.request import RequestTranslator
from cc_adapter.translator.response import translate_stream, collect_and_translate_nonstream
from cc_adapter.errors import AdapterError, AuthenticationError
from cc_adapter.models.openai import ChatCompletionRequest
from cc_adapter.admin import router as admin_router
from cc_adapter.admin.auth import set_password, validate_token
from cc_adapter.admin.state import init as admin_init, get_client as get_admin_client

logger = logging.getLogger(__name__)
config = AppConfig()
cc_client = CommandCodeClient(base_url=config.cc_base_url, api_key=config.cc_api_key[0] if config.cc_api_key else "")
request_translator = RequestTranslator()


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(log_format=config.log_format, log_level=config.log_level)
    set_password(config.admin_password)
    logger.info("CC Adapter starting — CC API: %s", config.cc_base_url)
    logger.info(
        "Admin panel: http://%s:%s/admin/", config.host if config.host != "0.0.0.0" else "localhost", config.port
    )
    if not config.cc_api_key:
        logger.warning("CC_ADAPTER_CC_API_KEY is not set. Set it via environment variable or .env file.")
    yield


app = FastAPI(title="Command Code Adapter", version="0.1.0", lifespan=lifespan)
app.add_middleware(CorrelationIDMiddleware)

admin_init(config, cc_client)
app.include_router(admin_router.router)

admin_static = StaticFiles(directory=Path(__file__).parent / "admin" / "static", html=True)
app.mount("/admin", admin_static, name="admin_static")


@app.exception_handler(AdapterError)
async def adapter_error_handler(request: Request, exc: AdapterError):
    logger.error("AdapterError: %s (status=%d)", exc.message, exc.status_code)
    return JSONResponse(status_code=exc.status_code, content=exc.to_openai_error())


@app.get("/")
async def root():
    return RedirectResponse(url="/admin/")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest, request: Request):
    if config.access_key:
        auth = request.headers.get("Authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else ""
        if token != config.access_key:
            if config.admin_password and validate_token(token):
                pass
            else:
                logger.warning("Authentication failed: invalid access key")
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

    logger.info(
        "Request: model=%s stream=%s messages=%d tools=%s tool_choice=%s",
        req.model,
        req.stream,
        len(req.messages),
        "yes" if req.tools else "no",
        req.tool_choice,
    )

    cc_body, cc_headers = request_translator.translate(req)
    cc_body["params"]["stream"] = True
    tools_available = bool(req.tools) and req.tool_choice != "none"

    start_time = time.time()

    current_client = get_admin_client() or cc_client
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


def _is_empty_error(chunk: str) -> bool:
    data = _chunk_payload(chunk)
    return bool(data and data.get("error", {}).get("message") == "Upstream model returned an empty response")


def _chunk_payload(chunk: str) -> dict | None:
    try:
        payload = chunk.removeprefix("data: ").strip()
        if payload == "[DONE]":
            return None
        data = json.loads(payload)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _has_visible_delta(chunk: str) -> bool:
    data = _chunk_payload(chunk)
    if not data:
        return False
    for choice in data.get("choices", []):
        delta = choice.get("delta") or {}
        if delta.get("content") or delta.get("tool_calls"):
            return True
    return False


def _has_streamable_delta(chunk: str) -> bool:
    data = _chunk_payload(chunk)
    if not data:
        return False
    for choice in data.get("choices", []):
        delta = choice.get("delta") or {}
        if delta.get("content") or delta.get("reasoning_content") or delta.get("tool_calls"):
            return True
    return False


async def _stream_with_retry(
    generate_fn,
    model: str,
    start_time: float,
    reasoning_effort: str | None = None,
    tools_available: bool = False,
):
    for attempt in range(2):
        cc_stream = generate_fn()
        translator = translate_stream(cc_stream, model, start_time, reasoning_effort, tools_available)
        buffer_until_visible = attempt == 0 and tools_available
        buffered_chunks: list[str] = []
        flushed_chunks = False
        should_retry = False
        emitted_visible_delta = False

        async for chunk in translator:
            if _has_visible_delta(chunk):
                emitted_visible_delta = True

            if attempt == 0 and not emitted_visible_delta and _is_empty_error(chunk):
                logger.warning("Empty upstream response (attempt 1/2), retrying...")
                await translator.aclose()
                should_retry = True
                break

            if buffer_until_visible:
                buffered_chunks.append(chunk)
                if _has_streamable_delta(chunk):
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
            return

        if should_retry:
            continue


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


def run():
    import uvicorn

    uvicorn.run(
        "cc_adapter.main:app",
        host=config.host,
        port=config.port,
        log_level=config.log_level.lower(),
    )
