import pytest
from unittest.mock import MagicMock

from cc_adapter.core.errors import AdapterError
from cc_adapter.core.retry import retry_on_empty


async def _gen_single(value):
    yield value


async def _gen_many(*values):
    for v in values:
        yield v


@pytest.mark.asyncio
async def test_retry_on_empty_first_attempt_succeeds():
    async def fake_translate(stream):
        return "hello"

    result = await retry_on_empty(
        lambda: _gen_single({"type": "text-delta", "text": "hello"}),
        fake_translate,
        MagicMock(),
        "test",
    )
    assert result == "hello"


@pytest.mark.asyncio
async def test_retry_on_empty_retries_once():
    call_count = 0

    async def fake_translate(stream):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise AdapterError(message="Upstream model returned an empty response", status_code=502)
        return "retried"

    result = await retry_on_empty(
        lambda: _gen_single("ignored"),
        fake_translate,
        MagicMock(),
        "test",
    )
    assert result == "retried"
    assert call_count == 2


@pytest.mark.asyncio
async def test_retry_on_empty_fails_twice():
    async def translate(stream):
        raise AdapterError(message="Upstream model returned an empty response", status_code=502)

    with pytest.raises(AdapterError):
        await retry_on_empty(
            lambda: _gen_single("ignored"),
            translate,
            MagicMock(),
            "test",
        )


@pytest.mark.asyncio
async def test_retry_on_empty_non_empty_error_not_retried():
    call_count = 0

    async def translate(stream):
        nonlocal call_count
        call_count += 1
        raise AdapterError(message="Some other error", status_code=502)

    with pytest.raises(AdapterError):
        await retry_on_empty(
            lambda: _gen_single("ignored"),
            translate,
            MagicMock(),
            "test",
        )
    assert call_count == 1
