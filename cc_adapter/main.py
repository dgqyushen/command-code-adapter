from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from cc_adapter.config import AppConfig
from cc_adapter.client import CommandCodeClient
from cc_adapter.translator.request import RequestTranslator
from cc_adapter.translator.response import translate_stream, collect_and_translate_nonstream
from cc_adapter.errors import AdapterError
from cc_adapter.models.openai import ChatCompletionRequest

logger = logging.getLogger(__name__)
config = AppConfig()
cc_client = CommandCodeClient(base_url=config.cc_base_url, api_key=config.cc_api_key)
request_translator = RequestTranslator()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=getattr(logging, config.log_level.upper(), logging.INFO))
    logger.info("CC Adapter starting — CC API: %s", config.cc_base_url)
    if not config.cc_api_key:
        logger.warning("CC_API_KEY is not set. Set it via environment variable or .env file.")
    yield


app = FastAPI(title="Command Code Adapter", version="0.1.0", lifespan=lifespan)


@app.exception_handler(AdapterError)
async def adapter_error_handler(request: Request, exc: AdapterError):
    return JSONResponse(status_code=exc.status_code, content=exc.to_openai_error())


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest):
    logger.info("Request: model=%s stream=%s messages=%d tools=%s",
                req.model, req.stream, len(req.messages), "yes" if req.tools else "no")

    cc_body, cc_headers = request_translator.translate(req)
    cc_body["params"]["stream"] = True  # always stream from CC internally

    try:
        cc_stream = cc_client.generate(cc_body, cc_headers)
    except AdapterError:
        raise
    except Exception as e:
        logger.exception("Unexpected error calling CC API")
        raise AdapterError(message=str(e), status_code=502)

    if req.stream:
        return StreamingResponse(
            translate_stream(cc_stream, req.model),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    else:
        result = await collect_and_translate_nonstream(cc_stream, req.model)
        return result


def run():
    import uvicorn
    uvicorn.run(
        "cc_adapter.main:app",
        host=config.host,
        port=config.port,
        log_level=config.log_level.lower(),
    )
