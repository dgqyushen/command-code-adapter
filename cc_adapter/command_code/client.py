from __future__ import annotations

import json
import structlog
from typing import AsyncGenerator, Any

import httpx

from cc_adapter.core.errors import map_upstream_error, AuthenticationError, TimeoutError_, UpstreamError
from cc_adapter.core.utils import generate_id
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
        logger.debug("sse.parse_error", preview=preview, error=str(e))
        return None
    if not isinstance(parsed, dict):
        preview = raw[:60]
        logger.debug("sse.parse_error", preview=preview, error="not_a_json_object")
        return None
    logger.debug("sse.raw_event", event_type=parsed.get("type", "?"))
    return parsed


_INSUFFICIENT_CREDITS_PHRASES = (
    "insufficient credits",
    "insufficient_credits",
)


def _is_retryable_error(status_code: int, body_text: str) -> bool:
    if status_code in (402, 429):
        return True
    if status_code == 400:
        lowered = body_text.lower()
        return any(phrase in lowered for phrase in _INSUFFICIENT_CREDITS_PHRASES)
    return False


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
        api_keys: list[str] | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._http_client = http_client
        self._owns_http_client = http_client is None
        self._max_connections = max_connections
        self._max_keepalive_connections = max_keepalive_connections
        self._http2 = _make_http2_safe(http2)

        self._session_id = generate_id("sess_", 16)

        if api_keys and len(api_keys) > 1:
            from cc_adapter.core.key_pool import KeyPool

            self.key_pool: KeyPool | None = KeyPool(api_keys, self.base_url)
        else:
            self.key_pool = None

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
        tried_keys: set[str] = set()
        last_error: Exception | None = None

        while True:
            if self.key_pool is not None:
                key = await self.key_pool.select_key(exclude=tried_keys)
            else:
                key = self.api_key

            if not key:
                raise AuthenticationError("CC_ADAPTER_CC_API_KEY is not configured")

            if key in tried_keys:
                if last_error is not None:
                    raise last_error
                raise AuthenticationError("CC_ADAPTER_CC_API_KEY is not configured")

            tried_keys.add(key)

            headers = make_cc_headers(key)
            headers["x-session-id"] = self._session_id
            headers.update(extra_headers or {})

            url = f"{self.base_url}/alpha/generate"

            client = self._client()
            try:
                async with client.stream("POST", url, json=body, headers=headers) as response:
                    if response.is_error:
                        error_body = await response.aread()
                        text = error_body.decode() if error_body else response.reason_phrase or "Unknown error"
                        logger.warning("upstream.error", status_code=response.status_code, error_type="cc_api_error")
                        mapped = map_upstream_error(response.status_code, text)

                        if _is_retryable_error(response.status_code, text):
                            last_error = mapped
                            continue

                        raise mapped

                    async for line in response.aiter_lines():
                        parsed = _parse_sse_line(line)
                        if parsed is not None:
                            yield parsed
                    return

            except httpx.TimeoutException:
                logger.warning("upstream.error", error_type="timeout", url=url)
                raise TimeoutError_("Command Code API request timed out")
            except httpx.RequestError as e:
                logger.warning("upstream.error", error_type=e.__class__.__name__, url=url)
                raise UpstreamError(f"Command Code API request failed: {e.__class__.__name__}")
