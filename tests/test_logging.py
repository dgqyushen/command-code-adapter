import json
import logging
import re

import pytest

from cc_adapter.core.logging import configure_logging, filter_sensitive_data, PrettyConsoleRenderer


def test_configure_logging_json_output(capsys):
    configure_logging(log_format="json", log_level="INFO")
    logging.getLogger("test_json").info("hello json")
    _, err = capsys.readouterr()
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
    _, err = capsys.readouterr()
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


def test_filter_sensitive_data_redacts_authorization():
    event = {
        "event": "api call",
        "authorization": "Bearer secret-token",
        "x-api-key": "my-api-key",
        "api_key": "another-key",
        "token": "some-token",
    }
    result = filter_sensitive_data(None, "info", event)
    assert result["authorization"] == "***"
    assert result["x-api-key"] == "***"
    assert result["api_key"] == "***"
    assert result["token"] == "***"


def test_filter_sensitive_data_redacts_messages():
    event = {
        "event": "chat",
        "messages": [{"role": "user", "content": "hello"}],
        "content": "some text",
    }
    result = filter_sensitive_data(None, "info", event)
    assert result["messages"] == "***"
    assert result["content"] == "***"


def test_filter_sensitive_data_recursive_list():
    event = {
        "event": "tool result",
        "results": [
            {"filePath": "/src/main.py", "oldString": "foo"},
            {"filePath": "/src/lib.py", "newString": "bar"},
        ],
    }
    result = filter_sensitive_data(None, "info", event)
    assert result["results"][0]["filePath"] == "***"
    assert result["results"][0]["oldString"] == "***"
    assert result["results"][1]["filePath"] == "***"
    assert result["results"][1]["newString"] == "***"


def test_filter_sensitive_data_case_insensitive():
    event = {
        "event": "api call",
        "Authorization": "Bearer secret",
        "X-Api-Key": "key123",
    }
    result = filter_sensitive_data(None, "info", event)
    assert result["Authorization"] == "***"
    assert result["X-Api-Key"] == "***"


def test_console_renderer_output_format():
    renderer = PrettyConsoleRenderer()
    event_dict = {
        "timestamp": "2024-01-15T10:30:45",
        "level": "info",
        "event": "http.done",
        "logger": "test",
        "method": "GET",
        "path": "/health",
        "status_code": 200,
        "elapsed": "0.123s",
        "extra_field": "value",
    }
    result = renderer(None, "info", event_dict)
    assert re.search(r"\d{2}:\d{2}:\d{2}", result), f"Missing timestamp in: {result}"
    assert "INFO" in result, f"Missing level in: {result}"
    assert "http.done" in result, f"Missing event in: {result}"
    assert "method=GET" in result, f"Missing method in: {result}"
    assert "path=/health" in result, f"Missing path in: {result}"
    assert "status_code=200" in result, f"Missing status_code in: {result}"
    assert "elapsed=0.123s" in result, f"Missing elapsed in: {result}"
    assert "extra_field=value" in result, f"Missing extra_field in: {result}"


def test_console_renderer_request_id_mapped_to_req():
    renderer = PrettyConsoleRenderer()
    event_dict = {
        "timestamp": "2024-01-15T10:30:45",
        "level": "info",
        "event": "http.done",
        "logger": "test",
        "method": "GET",
        "request_id": "abc123",
    }
    result = renderer(None, "info", event_dict)
    assert "req=abc123" in result, f"Missing req in: {result}"
    assert "request_id" not in result, f"request_id leaked in: {result}"


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
