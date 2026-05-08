from __future__ import annotations

import json
import logging
from typing import AsyncGenerator, Any

import httpx

from cc_adapter.errors import map_upstream_error, AuthenticationError

logger = logging.getLogger(__name__)


class CommandCodeClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    async def generate(
        self, body: dict[str, Any], extra_headers: dict[str, str] | None = None
    ) -> AsyncGenerator[dict[str, Any], None]:
        if not self.api_key:
            raise AuthenticationError("CC_API_KEY is not configured")

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "x-command-code-version": "0.25.2-adapter",
            "x-cli-environment": "production",
            "x-project-slug": "adapter",
            **(extra_headers or {}),
        }

        url = f"{self.base_url}/alpha/generate"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                async with client.stream("POST", url, json=body, headers=headers) as response:
                    if response.is_error:
                        error_body = await response.aread()
                        text = error_body.decode() if error_body else response.reason_phrase or "Unknown error"
                        raise map_upstream_error(response.status_code, text)

                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            parsed = json.loads(line)
                            logger.debug("CC raw event: type=%s", parsed.get("type", "?"))
                            yield parsed
                        except (ValueError, KeyError) as e:
                            logger.warning("Failed to parse CC event: %s", e)

            except httpx.TimeoutException:
                from cc_adapter.errors import TimeoutError_

                raise TimeoutError_("Command Code API request timed out")
            except httpx.HTTPStatusError as e:
                raise map_upstream_error(e.response.status_code, str(e))
