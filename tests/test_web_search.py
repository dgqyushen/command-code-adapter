import copy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import respx
from httpx import ASGITransport, AsyncClient, Response as HttpxResponse

from cc_adapter.main import app
from cc_adapter.core.config import AppConfig
from cc_adapter.core import runtime
from cc_adapter.providers.anthropic.response import (
    _has_web_search,
    _extract_web_search_calls,
    _build_second_cc_body,
)
from cc_adapter.providers.shared.web_search import (
    WEB_SEARCH_TOOL_DEFINITION,
    format_search_results,
    inject_web_search_tool,
    is_web_search_enabled,
)


def make_config(provider: str = "", deepseek_key: str = "", brave_key: str = "", tavily_key: str = ""):
    return SimpleNamespace(
        web_search_provider=provider,
        deepseek_api_key=deepseek_key,
        brave_api_key=brave_key,
        tavily_api_key=tavily_key,
    )


class TestWebSearchEnabled:
    def test_disabled_when_no_provider(self):
        assert is_web_search_enabled(make_config()) is False

    def test_disabled_when_empty_provider(self):
        assert is_web_search_enabled(make_config(provider="")) is False

    def test_disabled_when_config_none(self):
        assert is_web_search_enabled(None) is False

    def test_brave_enabled_with_key(self):
        assert is_web_search_enabled(make_config(provider="brave", brave_key="key")) is True

    def test_brave_disabled_without_key(self):
        assert is_web_search_enabled(make_config(provider="brave")) is False

    def test_tavily_enabled_with_key(self):
        assert is_web_search_enabled(make_config(provider="tavily", tavily_key="key")) is True

    def test_tavily_disabled_without_key(self):
        assert is_web_search_enabled(make_config(provider="tavily")) is False

    def test_deepseek_enabled_with_key(self):
        assert is_web_search_enabled(make_config(provider="deepseek", deepseek_key="key")) is True

    def test_deepseek_disabled_without_key(self):
        assert is_web_search_enabled(make_config(provider="deepseek")) is False

    def test_unknown_provider_returns_false(self):
        assert is_web_search_enabled(make_config(provider="unknown_provider")) is False

    def test_case_insensitive_provider_matching(self):
        assert is_web_search_enabled(make_config(provider="BRAVE", brave_key="key")) is True
        assert is_web_search_enabled(make_config(provider="  Brave  ", brave_key="key")) is True
        assert is_web_search_enabled(make_config(provider="DEEPSEEK", deepseek_key="key")) is True
        assert is_web_search_enabled(make_config(provider="TAVILY", tavily_key="key")) is True


class TestInjectWebSearchTool:
    def test_adds_web_search_tool(self):
        tools = [{"name": "other_tool", "input_schema": {}}]
        result = inject_web_search_tool(tools)
        assert len(result) == 2
        assert result[1] == WEB_SEARCH_TOOL_DEFINITION

    def test_does_not_duplicate_when_already_present(self):
        tools = [{"name": "web_search", "input_schema": {}}]
        result = inject_web_search_tool(tools)
        assert len(result) == 1

    def test_does_not_mutate_original_list(self):
        original = [{"name": "other_tool", "input_schema": {}}]
        original_copy = copy.deepcopy(original)
        inject_web_search_tool(original)
        assert original == original_copy

    def test_does_not_mutate_global_tool_definition(self):
        original_def = copy.deepcopy(WEB_SEARCH_TOOL_DEFINITION)
        tools = [{"name": "other_tool", "input_schema": {}}]
        result = inject_web_search_tool(tools)
        result[1]["name"] = "hacked"
        assert WEB_SEARCH_TOOL_DEFINITION == original_def

    def test_returns_new_list_not_reference(self):
        tools = [{"name": "other_tool", "input_schema": {}}]
        result = inject_web_search_tool(tools)
        assert result is not tools


class TestFormatSearchResults:
    def test_empty_results(self):
        assert format_search_results([]) == "No search results found."

    def test_single_result(self):
        results = [{"title": "Foo", "url": "https://foo.com", "snippet": "foo bar"}]
        out = format_search_results(results)
        assert "1. Foo" in out
        assert "URL: https://foo.com" in out
        assert "foo bar" in out

    def test_max_results_limits_output(self):
        results = [{"title": f"R{i}", "url": "", "snippet": ""} for i in range(20)]
        out = format_search_results(results, max_results=3)
        assert "1. R0" in out
        assert "3. R2" in out
        assert "4." not in out

    def test_missing_title_defaults_to_untitled(self):
        results = [{"url": "https://x.com"}]
        out = format_search_results(results)
        assert "Untitled" in out

    def test_none_title_handled(self):
        results = [{"title": None, "url": "https://x.com"}]
        out = format_search_results(results)
        assert "Untitled" in out

    def test_none_url_handled(self):
        results = [{"title": "Foo", "url": None, "snippet": "bar"}]
        out = format_search_results(results)
        assert "URL:" not in out

    def test_none_snippet_handled(self):
        results = [{"title": "Foo", "url": "", "snippet": None}]
        out = format_search_results(results)
        # Should not raise TypeError on len(None)
        assert "Foo" in out

    def test_truncation_exact_length(self):
        snippet = "x" * 600
        results = [{"title": "T", "url": "", "snippet": snippet}]
        out = format_search_results(results)
        assert "..." in out
        # Snippet portion should be exactly 500 chars (not 503)
        line = [l for l in out.split("\n") if "x" in l or "..." in l][0]
        stripped = line.strip()
        assert len(stripped) == 500
        assert stripped.endswith("...")

    def test_short_snippet_not_truncated(self):
        snippet = "x" * 100
        results = [{"title": "T", "url": "", "snippet": snippet}]
        out = format_search_results(results)
        assert "..." not in out


class TestWebSearchToolDefinition:
    def test_has_required_structure(self):
        assert WEB_SEARCH_TOOL_DEFINITION["name"] == "web_search"
        assert "description" in WEB_SEARCH_TOOL_DEFINITION
        assert WEB_SEARCH_TOOL_DEFINITION["input_schema"]["type"] == "object"
        assert "query" in WEB_SEARCH_TOOL_DEFINITION["input_schema"]["properties"]
        assert "query" in WEB_SEARCH_TOOL_DEFINITION["input_schema"]["required"]


class TestWebSearchResponseHelpers:
    def test_has_web_search_detects_tool_call(self):
        events = [
            {"type": "text-delta", "text": "hello"},
            {"type": "tool-call", "toolCallId": "c1", "toolName": "web_search", "input": {"query": "test"}},
            {"type": "finish", "finishReason": "tool_calls"},
        ]
        assert _has_web_search(events)

    def test_has_web_search_no_match(self):
        events = [
            {"type": "text-delta", "text": "hello"},
            {"type": "tool-call", "toolCallId": "c1", "toolName": "read", "input": {"path": "/tmp"}},
            {"type": "finish", "finishReason": "tool_calls"},
        ]
        assert not _has_web_search(events)

    def test_has_web_search_empty_events(self):
        assert not _has_web_search([])

    def test_extract_web_search_calls(self):
        events = [
            {"type": "text-delta", "text": "searching..."},
            {"type": "tool-call", "toolCallId": "c1", "toolName": "web_search", "input": {"query": "q1"}},
            {"type": "tool-call", "toolCallId": "c2", "toolName": "web_search", "input": {"query": "q2"}},
            {"type": "tool-call", "toolCallId": "c3", "toolName": "read", "input": {"path": "/tmp"}},
            {"type": "finish"},
        ]
        calls = _extract_web_search_calls(events)
        assert len(calls) == 2
        assert calls[0]["toolCallId"] == "c1"

    def test_build_second_cc_body_appends_messages(self):
        original_body = {
            "config": {},
            "params": {
                "model": "test-model",
                "messages": [
                    {"role": "user", "content": [{"type": "text", "text": "search please"}]}
                ],
                "tools": [{"name": "web_search", "description": "..."}],
                "max_tokens": 100,
                "stream": True,
            },
        }
        web_search_calls = [
            {"toolCallId": "c1", "toolName": "web_search", "input": {"query": "hello world"}},
        ]
        search_results = ["1. Result A\n   snippet"]

        body = _build_second_cc_body(original_body, web_search_calls, search_results)
        msgs = body["params"]["messages"]
        assert len(msgs) == 3  # user + assistant + tool
        assert msgs[1]["role"] == "assistant"
        assert msgs[1]["content"][0]["type"] == "tool-call"
        assert msgs[1]["content"][0]["toolCallId"] == "c1"
        assert msgs[2]["role"] == "tool"
        assert msgs[2]["content"][0]["type"] == "tool-result"
        assert msgs[2]["content"][0]["output"]["value"] == "1. Result A\n   snippet"

    def test_build_second_cc_body_does_not_mutate_original(self):
        original_body = {
            "config": {},
            "params": {
                "model": "x",
                "messages": [{"role": "user", "content": [{"type": "text", "text": "hi"}]}],
                "tools": [],
                "max_tokens": 100,
                "stream": True,
            },
        }
        original_copy = copy.deepcopy(original_body)
        _build_second_cc_body(original_body, [], [])
        assert original_body == original_copy

    def test_build_second_cc_body_mismatched_lengths_raises(self):
        with pytest.raises(ValueError):
            _build_second_cc_body(
                {"params": {"messages": []}},
                [{"toolCallId": "c1", "toolName": "web_search", "input": {"query": "q"}}],
                [],
            )


WEB_SEARCH_STREAM_EVENTS = (
    'data: {"type":"text-delta","text":"Let me search"}\n\n'
    'data: {"type":"tool-call","toolCallId":"call_1","toolName":"web_search","input":{"query":"latest AI news"}}\n\n'
    'data: {"type":"finish","finishReason":"tool_calls","totalUsage":{"inputTokens":10,"outputTokens":5}}\n\n'
)

SECOND_STREAM_EVENTS = (
    'data: {"type":"text-delta","text":"Here are the results"}\n\n'
    'data: {"type":"finish","finishReason":"end_turn","totalUsage":{"inputTokens":20,"outputTokens":10}}\n\n'
)

NO_SEARCH_STREAM_EVENTS = (
    'data: {"type":"text-delta","text":"Hello"}\n\n'
    'data: {"type":"finish","finishReason":"end_turn","totalUsage":{"inputTokens":10,"outputTokens":5}}\n\n'
)


@pytest.mark.asyncio
async def test_router_stream_no_web_search_passes_through(monkeypatch):
    cfg = AppConfig(
        cc_api_key="test-key",
        web_search_provider="deepseek",
        deepseek_api_key="sk-test",
    )
    monkeypatch.setattr(runtime, "_config", cfg)
    monkeypatch.setattr(runtime, "_cc_client", None)

    async with respx.mock(base_url="https://api.commandcode.ai", assert_all_called=False) as respx_mock:
        respx_mock.post("/alpha/generate").mock(
            return_value=HttpxResponse(200, text=NO_SEARCH_STREAM_EVENTS)
        )
        respx_mock.get("https://registry.npmjs.org/command-code/latest").mock(
            return_value=HttpxResponse(200, json={"version": "0.25.2"})
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/v1/messages",
                json={
                    "model": "claude-sonnet-4-6",
                    "max_tokens": 100,
                    "messages": [{"role": "user", "content": "say hello"}],
                    "stream": True,
                },
            )

        assert resp.status_code == 200
        assert "Hello" in resp.text


@pytest.mark.asyncio
async def test_router_stream_web_search_disabled_uses_original_flow(monkeypatch):
    cfg = AppConfig(cc_api_key="test-key")
    monkeypatch.setattr(runtime, "_config", cfg)
    monkeypatch.setattr(runtime, "_cc_client", None)

    async with respx.mock(base_url="https://api.commandcode.ai", assert_all_called=False) as respx_mock:
        respx_mock.post("/alpha/generate").mock(
            return_value=HttpxResponse(200, text=NO_SEARCH_STREAM_EVENTS)
        )
        respx_mock.get("https://registry.npmjs.org/command-code/latest").mock(
            return_value=HttpxResponse(200, json={"version": "0.25.2"})
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/v1/messages",
                json={
                    "model": "claude-sonnet-4-6",
                    "max_tokens": 100,
                    "messages": [{"role": "user", "content": "say hello"}],
                    "stream": True,
                },
            )

        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_router_stream_with_web_search(monkeypatch):
    cfg = AppConfig(
        cc_api_key="test-key",
        web_search_provider="deepseek",
        deepseek_api_key="sk-test",
    )
    monkeypatch.setattr(runtime, "_config", cfg)
    monkeypatch.setattr(runtime, "_cc_client", None)

    async def mock_execute_search(query, config):
        return [{"title": "Result", "url": "", "snippet": "found"}]
    monkeypatch.setattr("cc_adapter.providers.shared.web_search.execute_search", mock_execute_search)

    async with respx.mock(base_url="https://api.commandcode.ai", assert_all_called=False) as respx_mock:
        respx_mock.post("/alpha/generate").mock(
            side_effect=[
                HttpxResponse(200, text=WEB_SEARCH_STREAM_EVENTS),
                HttpxResponse(200, text=SECOND_STREAM_EVENTS),
            ]
        )
        respx_mock.get("https://registry.npmjs.org/command-code/latest").mock(
            return_value=HttpxResponse(200, json={"version": "0.25.2"})
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/v1/messages",
                json={
                    "model": "claude-sonnet-4-6",
                    "max_tokens": 100,
                    "messages": [{"role": "user", "content": "search for AI news"}],
                    "stream": True,
                },
            )

        assert resp.status_code == 200
        assert "Here are the results" in resp.text
