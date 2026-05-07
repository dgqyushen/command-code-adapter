from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from cc_adapter.config import AppConfig
from cc_adapter.client import CommandCodeClient
from cc_adapter.translator.request import RequestTranslator
from cc_adapter.translator.response import translate_stream, collect_and_translate_nonstream
from cc_adapter.errors import AdapterError, AuthenticationError
from cc_adapter.models.openai import ChatCompletionRequest
from cc_adapter.admin import router as admin_router
from cc_adapter.admin.auth import set_password
from cc_adapter.admin.state import init as admin_init, get_client as get_admin_client

logger = logging.getLogger(__name__)
config = AppConfig()
cc_client = CommandCodeClient(base_url=config.cc_base_url, api_key=config.cc_api_key[0] if config.cc_api_key else "")
request_translator = RequestTranslator()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log_level = getattr(logging, config.log_level.upper(), logging.INFO)
    logging.getLogger().setLevel(log_level)
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(level=log_level, force=True)
    set_password(config.admin_password)
    logger.info("CC Adapter starting — CC API: %s", config.cc_base_url)
    logger.info("Admin panel: http://%s:%s/admin/", config.host if config.host != "0.0.0.0" else "localhost", config.port)
    if not config.cc_api_key:
        logger.warning("CC_API_KEY is not set. Set it via environment variable or .env file.")
    yield


app = FastAPI(title="Command Code Adapter", version="0.1.0", lifespan=lifespan)

admin_init(config, cc_client)
app.include_router(admin_router.router)

admin_static = StaticFiles(directory=Path(__file__).parent / "admin" / "static", html=True)
app.mount("/admin", admin_static, name="admin_static")


@app.exception_handler(AdapterError)
async def adapter_error_handler(request: Request, exc: AdapterError):
    return JSONResponse(status_code=exc.status_code, content=exc.to_openai_error())


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest, request: Request):
    if config.access_key:
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer ") or auth[7:] != config.access_key:
            return JSONResponse(status_code=401, content={
                "error": {
                    "message": "Invalid API key",
                    "type": "invalid_request_error",
                    "code": "invalid_api_key",
                }
            })

    logger.info("Request: model=%s stream=%s messages=%d tools=%s",
                req.model, req.stream, len(req.messages), "yes" if req.tools else "no")

    cc_body, cc_headers = request_translator.translate(req)
    cc_body["params"]["stream"] = True

    start_time = time.time()

    current_client = get_admin_client() or cc_client
    if not current_client.api_key:
        raise AuthenticationError("CC_API_KEY is not configured")

    cc_stream = current_client.generate(cc_body, cc_headers)

    if req.stream:
        return StreamingResponse(
            translate_stream(cc_stream, req.model, start_time),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    else:
        result = await collect_and_translate_nonstream(cc_stream, req.model, start_time)
        return result


def run():
    import uvicorn
    uvicorn.run(
        "cc_adapter.main:app",
        host=config.host,
        port=config.port,
        log_level=config.log_level.lower(),
    )
