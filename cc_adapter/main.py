from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from cc_adapter.core.config import AppConfig
from cc_adapter.command_code.client import CommandCodeClient
from cc_adapter.core.logging import configure_logging, CorrelationIDMiddleware
from cc_adapter.core.errors import AdapterError
from cc_adapter.core.auth import set_password
from cc_adapter.core.runtime import init as runtime_init, get_client as get_runtime_client, get_config
from cc_adapter.providers.openai.router import router as openai_router
from cc_adapter.providers.anthropic.router import router as anthropic_router
from cc_adapter.admin import router as admin_router
from cc_adapter.catalog.models_data import MODELS_DATA

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = get_config() or AppConfig()
    configure_logging(log_format=cfg.log_format, log_level=cfg.log_level)
    set_password(cfg.admin_password)
    logger.info("CC Adapter starting — CC API: %s", cfg.cc_base_url)
    logger.info("Admin panel: http://%s:%s/admin/", cfg.host if cfg.host != "0.0.0.0" else "localhost", cfg.port)
    if not cfg.cc_api_key:
        logger.warning("CC_ADAPTER_CC_API_KEY is not set. Set it via environment variable or .env file.")
    yield
    cc_client = get_runtime_client()
    if cc_client is not None:
        await cc_client.aclose()


app = FastAPI(title="Command Code Adapter", version="0.1.0", lifespan=lifespan)
app.add_middleware(CorrelationIDMiddleware)

cfg = AppConfig()
runtime_init(
    cfg,
    CommandCodeClient(
        base_url=cfg.cc_base_url,
        api_key=cfg.cc_api_key[0] if cfg.cc_api_key else "",
        max_connections=cfg.http_max_connections,
        max_keepalive_connections=cfg.http_max_keepalive_connections,
        http2=cfg.http2,
    ),
)
app.include_router(openai_router)
app.include_router(anthropic_router)
app.include_router(admin_router.router)

admin_static = StaticFiles(directory=Path(__file__).parent / "admin" / "static", html=True)
app.mount("/admin", admin_static, name="admin_static")


@app.get("/v1/models")
async def list_models():
    return {"object": "list", "data": MODELS_DATA}


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


def run():
    import uvicorn

    cfg = get_config() or AppConfig()
    uvicorn.run(
        "cc_adapter.main:app",
        host=cfg.host,
        port=cfg.port,
        log_level=cfg.log_level.lower(),
    )
