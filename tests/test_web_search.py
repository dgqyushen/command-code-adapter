import copy
from types import SimpleNamespace

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
