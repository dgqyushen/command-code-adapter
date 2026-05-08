from __future__ import annotations

import json
import logging
from typing import AsyncGenerator, Any

import httpx

from cc_adapter.errors import map_upstream_error, AuthenticationError, TimeoutError_
from cc_adapter.headers import make_cc_headers

logger = logging.getLogger(__name__)


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
        logger.warning("Failed to parse CC event line %r: %s", preview, e)
        return None
    if not isinstance(parsed, dict):
        preview = raw[:60]
        logger.warning("Failed to parse CC event line %r: not a JSON object", preview)
        return None
    logger.debug("CC raw event: type=%s", parsed.get("type", "?"))
    return parsed


class CommandCodeClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    async def generate(
        self, body: dict[str, Any], extra_headers: dict[str, str] | None = None
    ) -> AsyncGenerator[dict[str, Any], None]:
        if not self.api_key:
            raise AuthenticationError("CC_ADAPTER_CC_API_KEY is not configured")

        headers = make_cc_headers(self.api_key)
        headers.update(extra_headers or {})

        url = f"{self.base_url}/alpha/generate"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                async with client.stream("POST", url, json=body, headers=headers) as response:
                    if response.is_error:
                        error_body = await response.aread()
                        text = error_body.decode() if error_body else response.reason_phrase or "Unknown error"
                        logger.warning("CC API error: status=%d body=%s", response.status_code, text[:500])
                        raise map_upstream_error(response.status_code, text)

                    async for line in response.aiter_lines():
                        parsed = _parse_sse_line(line)
                        if parsed is not None:
                            yield parsed

            except httpx.TimeoutException:
                logger.warning("CC API request timed out (url=%s)", url)
                raise TimeoutError_("Command Code API request timed out")
            except httpx.HTTPStatusError as e:
                logger.warning(
                    "CC API HTTP error: status=%d url=%s",
                    e.response.status_code,
                    url,
                )
                raise map_upstream_error(e.response.status_code, str(e))
