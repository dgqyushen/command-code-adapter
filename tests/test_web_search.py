import copy

import pytest

from cc_adapter.providers.shared.web_search import (
    WEB_SEARCH_TOOL_DEFINITION,
    has_anthropic_web_search_tool,
    inject_web_search_tool,
    is_web_search_enabled,
)
from cc_adapter.core.config import AppConfig


class TestWebSearchEnabled:
    def test_disabled_when_config_none(self):
        assert is_web_search_enabled(None) is False

    def test_disabled_when_no_provider(self):
        cfg = AppConfig(web_search_provider="")
        assert is_web_search_enabled(cfg) is False

    def test_disabled_when_deepseek_no_key(self):
        cfg = AppConfig(web_search_provider="deepseek", deepseek_api_key="")
        assert is_web_search_enabled(cfg) is False

    def test_deepseek_enabled_with_key(self):
        cfg = AppConfig(web_search_provider="deepseek", deepseek_api_key="sk-key")
        assert is_web_search_enabled(cfg) is True

    def test_unknown_provider_returns_false(self):
        cfg = AppConfig(web_search_provider="unknown")
        assert is_web_search_enabled(cfg) is False

    def test_case_insensitive_provider(self):
        cfg = AppConfig(web_search_provider="DEEPSEEK", deepseek_api_key="sk-key")
        assert is_web_search_enabled(cfg) is True


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


class TestWebSearchToolDefinition:
    def test_has_required_structure(self):
        assert WEB_SEARCH_TOOL_DEFINITION["name"] == "web_search"
        assert "description" in WEB_SEARCH_TOOL_DEFINITION
        assert WEB_SEARCH_TOOL_DEFINITION["input_schema"]["type"] == "object"
        assert "query" in WEB_SEARCH_TOOL_DEFINITION["input_schema"]["properties"]
        assert "query" in WEB_SEARCH_TOOL_DEFINITION["input_schema"]["required"]


class TestHasAnthropicWebSearchTool:
    def test_detects_server_tool_dict(self):
        tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}]
        assert has_anthropic_web_search_tool(tools) is True

    def test_ignores_function_tool_named_web_search(self):
        tools = [{"name": "web_search", "input_schema": {"type": "object"}}]
        assert has_anthropic_web_search_tool(tools) is False

    def test_ignores_other_server_tools(self):
        tools = [{"type": "code_execution_20250522", "name": "code_execution"}]
        assert has_anthropic_web_search_tool(tools) is False

    def test_false_for_empty_tools(self):
        assert has_anthropic_web_search_tool([]) is False
