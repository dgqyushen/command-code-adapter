from __future__ import annotations

import logging
from typing import AsyncGenerator, Awaitable, Callable, TypeVar

from cc_adapter.core.errors import AdapterError

T = TypeVar("T")


async def retry_on_empty(
    generate_fn: Callable[[], AsyncGenerator[dict, None]],
    translate_fn: Callable[[AsyncGenerator[dict, None]], Awaitable[T]],
    logger: logging.Logger,
    label: str = "",
) -> T:
    for attempt in range(2):
        cc_stream = generate_fn()
        try:
            return await translate_fn(cc_stream)
        except AdapterError as e:
            if attempt == 0 and "empty response" in e.message.lower():
                logger.warning("%s: Empty upstream response (attempt 1/2), retrying...", label)
                continue
            raise


async def stream_with_retry(
    generate_fn: Callable[[], AsyncGenerator[dict, None]],
    translate_fn: Callable[[AsyncGenerator[dict, None]], AsyncGenerator[str, None]],
    logger: logging.Logger,
    label: str = "",
    error_fn: Callable[[str], str] | None = None,
) -> AsyncGenerator[str, None]:
    for attempt in range(2):
        cc_stream = generate_fn()
        translator = translate_fn(cc_stream)
        yielded_any = False
        try:
            async for chunk in translator:
                yielded_any = True
                yield chunk
        except AdapterError as e:
            if not yielded_any and attempt == 0 and "empty response" in e.message.lower():
                logger.warning("%s: Empty upstream response (attempt 1/2), retrying...", label)
                continue
            if error_fn:
                yield error_fn(e.message)
            return
        return
