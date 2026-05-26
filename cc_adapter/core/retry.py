from __future__ import annotations

from typing import AsyncGenerator, Awaitable, Callable, TypeVar

import structlog

from cc_adapter.core.errors import AdapterError

T = TypeVar("T")


async def retry_on_empty(
    generate_fn: Callable[[], AsyncGenerator[dict, None]],
    translate_fn: Callable[[AsyncGenerator[dict, None]], Awaitable[T]],
    logger: structlog.stdlib.BoundLogger,
    label: str = "",
) -> T:
    cc_stream = generate_fn()
    return await translate_fn(cc_stream)


async def stream_with_retry(
    generate_fn: Callable[[], AsyncGenerator[dict, None]],
    translate_fn: Callable[[AsyncGenerator[dict, None]], AsyncGenerator[str, None]],
    logger: structlog.stdlib.BoundLogger,
    label: str = "",
    error_fn: Callable[[str], str] | None = None,
    buffer_detector: _BufferDetector | None = None,
) -> AsyncGenerator[str, None]:
    if buffer_detector:
        for attempt in range(2):
            cc_stream = generate_fn()
            translator = translate_fn(cc_stream)
            yielded_any = False
            should_retry = False

            try:
                if attempt == 0:
                    async for chunk in translator:
                        buffer_detector.feed(chunk)
                        if buffer_detector.after_flush:
                            data = buffer_detector._chunk_payload(chunk)
                            if not buffer_detector._visible_seen and buffer_detector._is_empty_error(data):
                                should_retry = True
                                await translator.aclose()
                                break
                            yield chunk
                            yielded_any = True
                            continue

                        if buffer_detector.should_flush():
                            for c in buffer_detector.drain():
                                yield c
                                yielded_any = True
                            buffer_detector.after_flush = True
                            continue

                        data = buffer_detector._chunk_payload(chunk)
                        if buffer_detector._is_empty_error(data):
                            for c in buffer_detector.retry_chunks():
                                yield c
                                yielded_any = True
                            should_retry = True
                            await translator.aclose()
                            break
                    else:
                        if buffer_detector.should_retry():
                            should_retry = True
                            for c in buffer_detector.retry_chunks():
                                yield c
                                yielded_any = True
                        else:
                            for c in buffer_detector.drain():
                                yield c
                                yielded_any = True
                        await translator.aclose()
                else:
                    async for chunk in translator:
                        yielded_any = True
                        yield chunk
            except AdapterError as e:
                if not yielded_any and attempt == 0 and "empty response" in e.message.lower():
                    should_retry = True
                elif error_fn:
                    yield error_fn(e.message)
                    return
                else:
                    return

            if should_retry:
                logger.warning("%s: Empty upstream response (attempt %d/2), retrying...", label, attempt + 1)
                continue

            return
    else:
        cc_stream = generate_fn()
        translator = translate_fn(cc_stream)
        try:
            async for chunk in translator:
                yield chunk
        except AdapterError as e:
            if error_fn:
                yield error_fn(e.message)
            return


class _BufferDetector:
    """Buffers SSE chunks to detect empty-response errors before streaming to the client.

    State flow: feed chunks -> should_flush? (seen a visible delta) -> after_flush mode.
    In before_flush mode, chunks are buffered. Once a visible delta is found, all
    buffered chunks are drained and subsequent ones pass through immediately.
    If an empty-error is detected before flushing, the buffer is filtered for retry.
    """

    def __init__(self):
        self._buffer: list[str] = []
        self._flushed = False
        self._visible_seen = False
        self.after_flush = False

    def feed(self, chunk: str) -> None:
        if self._flushed:
            return
        self._buffer.append(chunk)

    def _chunk_payload(self, chunk: str) -> dict | None:
        import json

        try:
            payload = chunk.removeprefix("data: ").strip()
            if payload == "[DONE]":
                return None
            data = json.loads(payload)
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def _has_streamable_delta(self, data: dict | None) -> bool:
        if not data:
            return False
        for choice in data.get("choices", []):
            delta = choice.get("delta") or {}
            if delta.get("content") or delta.get("tool_calls") or delta.get("reasoning_content"):
                return True
        return False

    def _has_visible_delta(self, data: dict | None) -> bool:
        if not data:
            return False
        for choice in data.get("choices", []):
            delta = choice.get("delta") or {}
            if delta.get("content") or delta.get("tool_calls"):
                return True
        return False

    def _is_empty_error(self, data: dict | None) -> bool:
        return bool(data and data.get("error", {}).get("message") == "Upstream model returned an empty response")

    def should_flush(self) -> bool:
        if self._flushed or not self._buffer:
            return False
        last = self._chunk_payload(self._buffer[-1])
        if last is None:
            return False
        if self._has_streamable_delta(last):
            if self._has_visible_delta(last):
                self._visible_seen = True
            self._flushed = True
            return True
        return False

    def should_retry(self) -> bool:
        if not self._buffer:
            return False
        for chunk in self._buffer:
            data = self._chunk_payload(chunk)
            if self._is_empty_error(data):
                return True
        return False

    def drain(self) -> list[str]:
        result = list(self._buffer)
        self._buffer.clear()
        return result

    def retry_chunks(self) -> list[str]:
        result = []
        for chunk in self._buffer:
            if chunk.startswith("data: [DONE]"):
                continue
            data = self._chunk_payload(chunk)
            if self._is_empty_error(data):
                continue
            result.append(chunk)
        self._buffer.clear()
        return result
