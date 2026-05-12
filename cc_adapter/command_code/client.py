from __future__ import annotations

import json
import logging
import structlog
from typing import AsyncGenerator, Any

import httpx

from cc_adapter.core.errors import map_upstream_error, AuthenticationError, TimeoutError_, UpstreamError
from cc_adapter.command_code.headers import make_cc_headers

logger = structlog.get_logger(__name__)


def _parse_sse_line(raw: str) -> dict[str, Any] | None:
    """Parse a single SSE line. Returns None for lines to skip."""
    line = raw.strip()
    if not line:
        return None
    if line.startswith("data:"):
        line = line[5:].lstrip()
    if line == "[DONE]":
        return None
    try:
        parsed = json.loads(line)
    except ValueError as e:
        preview = raw[:60]
        logger.debug("Failed to parse CC event line %r: %s", preview, e)
        return None
    if not isinstance(parsed, dict):
        preview = raw[:60]
        logger.debug("Failed to parse CC event line %r: not a JSON object", preview)
        return None
    logger.debug("CC raw event: type=%s", parsed.get("type", "?"))
    return parsed


def _make_http2_safe(http2: bool) -> bool:
    if not http2:
        return False
    try:
        import h2  # noqa: F401
    except ImportError:
        logger.warning("http2=True configured but 'h2' package is not installed. Falling back to HTTP/1.1.")
        return False
    return http2


class CommandCodeClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: float = 60.0,
        http_client: httpx.AsyncClient | None = None,
        max_connections: int = 200,
        max_keepalive_connections: int = 50,
        http2: bool = False,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._http_client = http_client
        self._owns_http_client = http_client is None
        self._max_connections = max_connections
        self._max_keepalive_connections = max_keepalive_connections
        self._http2 = _make_http2_safe(http2)

    def _client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=self.timeout,
                limits=httpx.Limits(
                    max_connections=self._max_connections,
                    max_keepalive_connections=self._max_keepalive_connections,
                ),
                http2=self._http2,
            )
            self._owns_http_client = True
        return self._http_client

    async def aclose(self) -> None:
        if self._http_client is not None and self._owns_http_client:
            await self._http_client.aclose()

    async def generate(
        self, body: dict[str, Any], extra_headers: dict[str, str] | None = None
    ) -> AsyncGenerator[dict[str, Any], None]:
        if not self.api_key:
            raise AuthenticationError("CC_ADAPTER_CC_API_KEY is not configured")

        headers = make_cc_headers(self.api_key)
        headers.update(extra_headers or {})

        url = f"{self.base_url}/alpha/generate"

        client = self._client()
        try:
            async with client.stream("POST", url, json=body, headers=headers) as response:
                if response.is_error:
                    error_body = await response.aread()
                    text = error_body.decode() if error_body else response.reason_phrase or "Unknown error"
                    logger.warning("upstream.error", status_code=response.status_code, error_type="cc_api_error")
                    raise map_upstream_error(response.status_code, text)

                async for line in response.aiter_lines():
                    parsed = _parse_sse_line(line)
                    if parsed is not None:
                        yield parsed

        except httpx.TimeoutException:
            logger.warning("upstream.error", error_type="timeout", url=url)
            raise TimeoutError_("Command Code API request timed out")
        except httpx.RequestError as e:
            logger.warning("upstream.error", error_type=e.__class__.__name__, url=url)
            raise UpstreamError(f"Command Code API request failed: {e.__class__.__name__}")
