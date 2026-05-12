import io
import json
import logging

import pytest

from cc_adapter.core.logging import configure_logging, filter_sensitive_data


def test_configure_logging_json_output(capsys):
    configure_logging(log_format="json", log_level="INFO")
    logging.getLogger("test_json").info("hello json")
    out, err = capsys.readouterr()
    lines = err.strip().splitlines()
    for line in lines:
        if "hello json" in line:
            parsed = json.loads(line)
            assert parsed.get("event") == "hello json"
            assert parsed.get("level") == "info"
            assert parsed.get("logger") == "test_json"
            assert "timestamp" in parsed
            break
    else:
        pytest.fail(f"No JSON log line with 'hello json' found in: {err}")


def test_configure_logging_level_respected(capsys):
    configure_logging(log_format="json", log_level="WARNING")
    logging.getLogger("test_level").debug("should not appear")
    logging.getLogger("test_level").info("should not appear")
    logging.getLogger("test_level").warning("should appear")
    out, err = capsys.readouterr()
    assert "should appear" in err
    assert "should not appear" not in err


def test_filter_sensitive_data_redacts_tool_fields():
    event = {
        "event": "tool call",
        "filePath": "/src/main.py",
        "oldString": "def foo():",
        "newString": "def bar():",
        "path": "/src/main.py",
        "old_str": "foo",
        "new_str": "bar",
        "normal_field": "keep me",
    }
    result = filter_sensitive_data(None, "info", event)
    assert result["filePath"] == "***"
    assert result["oldString"] == "***"
    assert result["newString"] == "***"
    assert result["path"] == "***"
    assert result["old_str"] == "***"
    assert result["new_str"] == "***"
    assert result["normal_field"] == "keep me"


def test_filter_sensitive_data_redacts_nested():
    event = {
        "event": "tool call",
        "input": {
            "filePath": "/src/main.py",
            "oldString": "foo",
        },
    }
    result = filter_sensitive_data(None, "info", event)
    assert result["input"]["filePath"] == "***"
    assert result["input"]["oldString"] == "***"


def test_correlation_id_middleware_adds_header():
    from cc_adapter.main import app
    from httpx import AsyncClient, ASGITransport

    transport = ASGITransport(app=app)

    async def test():
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health")
            assert resp.status_code == 200
            assert "X-Request-ID" in resp.headers
            assert len(resp.headers["X-Request-ID"]) > 0

    import asyncio

    asyncio.run(test())


def test_correlation_id_middleware_preserves_header():
    from cc_adapter.main import app
    from httpx import AsyncClient, ASGITransport

    transport = ASGITransport(app=app)

    async def test():
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health", headers={"X-Request-ID": "my-custom-id"})
            assert resp.status_code == 200
            assert resp.headers["X-Request-ID"] == "my-custom-id"

    import asyncio

    asyncio.run(test())
