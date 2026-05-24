from __future__ import annotations

import structlog
from typing import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from cc_adapter.providers.anthropic.models import AnthropicRequest, AnthropicResponse
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


async def _stream_with_web_search(
    client: CommandCodeClient,
    cc_body: dict,
    cc_headers: dict,
    model: str,
) -> AsyncGenerator[str, None]:
    from cc_adapter.providers.anthropic.response import (
        _has_web_search,
        _extract_web_search_calls,
        _build_second_cc_body,
        _events_to_list,
        _list_to_stream,
    )
    from cc_adapter.providers.shared.web_search import execute_search, format_search_results

    config = get_config()

    injected = cc_body.get("params", {}).pop("_adapter_web_search", False)

    try:
        events = await _events_to_list(client.generate(cc_body, cc_headers))
    except Exception as e:
        yield _anthropic_sse_error(str(e))
        return

    if not _has_web_search(events, injected=injected):
        async for chunk in translate_anthropic_stream(_list_to_stream(events), model):
            yield chunk
        return

    web_search_calls = _extract_web_search_calls(events)
    import asyncio

    async def _run_one_search(query):
        if not query:
            return "Error: empty search query"
        results = await execute_search(query, config)
        return format_search_results(results)

    queries = [tc.get("input", {}).get("query", "") for tc in web_search_calls]
    search_results = await asyncio.gather(*[_run_one_search(q) for q in queries])

    second_body = _build_second_cc_body(cc_body, web_search_calls, search_results)

    async for chunk in stream_with_retry(
        lambda sc=second_body, sh=cc_headers: client.generate(sc, sh),
        lambda stream: translate_anthropic_stream(stream, model),
        logger,
        "anthropic.websearch.stream",
        error_fn=lambda msg: format_sse("error", {"type": "error", "error": {"type": "api_error", "message": msg}}),
    ):
        yield chunk


async def _nonstream_with_web_search(
    client: CommandCodeClient,
    cc_body: dict,
    cc_headers: dict,
    model: str,
) -> AnthropicResponse:
    from cc_adapter.providers.anthropic.response import (
        _has_web_search,
        _extract_web_search_calls,
        _build_second_cc_body,
        _events_to_list,
        collect_and_translate_anthropic_nonstream,
    )
    from cc_adapter.providers.shared.web_search import execute_search, format_search_results

    config = get_config()

    injected = cc_body.get("params", {}).pop("_adapter_web_search", False)

    events = await _events_to_list(client.generate(cc_body, cc_headers))

    injected = cc_body.get("params", {}).get("_adapter_web_search", False)
    if not _has_web_search(events, injected=injected):

        async def _s():
            for e in events:
                yield e

        return await collect_and_translate_anthropic_nonstream(_s(), model)

    web_search_calls = _extract_web_search_calls(events)
    import asyncio

    async def _run_one_search(query):
        if not query:
            return "Error: empty search query"
        results = await execute_search(query, config)
        return format_search_results(results)

    queries = [tc.get("input", {}).get("query", "") for tc in web_search_calls]
    search_results = await asyncio.gather(*[_run_one_search(q) for q in queries])

    second_body = _build_second_cc_body(cc_body, web_search_calls, search_results)

    return await retry_on_empty(
        lambda sc=second_body, sh=cc_headers: client.generate(sc, sh),
        lambda stream: collect_and_translate_anthropic_nonstream(stream, model),
        logger,
        "anthropic.websearch.nonstream",
    )


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

    from cc_adapter.providers.shared.web_search import is_web_search_enabled

    config = get_config()
    web_search_enabled = is_web_search_enabled(config)

    try:
        if req.stream:
            if web_search_enabled:
                return StreamingResponse(
                    _stream_with_web_search(current_client, cc_body, cc_headers, req.model),
                    media_type="text/event-stream",
                    headers=STREAMING_HEADERS,
                )
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
            if web_search_enabled:
                return await _nonstream_with_web_search(current_client, cc_body, cc_headers, req.model)
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
