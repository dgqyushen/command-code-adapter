from cc_adapter.providers.shared.tool_mapping import (
    make_tool_call_block,
    make_tool_result_block,
    normalize_schema,
    normalize_args,
    translate_tool_choice,
)
from cc_adapter.providers.shared.tool_mapping import SCHEMA_PARAM_MAP


class TestNormalizeSchema:
    def test_maps_filePath_to_path(self):
        schema = {"type": "object", "properties": {"filePath": {"type": "string"}}}
        result = normalize_schema(schema)
        assert result["properties"] == {"path": {"type": "string"}}

    def test_maps_edit_params(self):
        schema = {
            "type": "object",
            "properties": {
                "filePath": {"type": "string"},
                "oldString": {"type": "string"},
                "newString": {"type": "string"},
            },
            "required": ["filePath", "oldString", "newString"],
        }
        result = normalize_schema(schema)
        assert result["properties"] == {
            "path": {"type": "string"},
            "old_str": {"type": "string"},
            "new_str": {"type": "string"},
        }
        assert result["required"] == ["path", "old_str", "new_str"]

    def test_preserves_unmapped_params(self):
        schema = {"type": "object", "properties": {"content": {"type": "string"}, "command": {"type": "string"}}}
        result = normalize_schema(schema)
        assert result["properties"] == {"content": {"type": "string"}, "command": {"type": "string"}}

    def test_handles_empty_schema(self):
        assert normalize_schema({}) == {}

    def test_handles_none(self):
        assert normalize_schema(None) is None


class TestNormalizeArgs:
    def test_file_tool_maps_path_to_filePath(self):
        result = normalize_args("read", {"path": "/tmp/test"})
        assert result == {"filePath": "/tmp/test"}

    def test_file_tool_maps_file_path_to_filePath(self):
        result = normalize_args("write", {"file_path": "/tmp/test"})
        assert result == {"filePath": "/tmp/test"}

    def test_non_file_tool_preserves_path(self):
        result = normalize_args("grep", {"path": "/src", "pattern": "foo"})
        assert result == {"path": "/src", "pattern": "foo"}

    def test_non_file_tool_preserves_path_for_glob(self):
        result = normalize_args("glob", {"path": "/src", "pattern": "*.py"})
        assert result == {"path": "/src", "pattern": "*.py"}

    def test_maps_old_str_to_oldString(self):
        result = normalize_args("edit", {"old_str": "foo", "new_str": "bar"})
        assert result == {"oldString": "foo", "newString": "bar"}

    def test_file_tool_maps_path_and_str_params(self):
        result = normalize_args("edit", {"file_path": "/tmp/x", "old_str": "a", "new_str": "b"})
        assert result == {"filePath": "/tmp/x", "oldString": "a", "newString": "b"}

    def test_handles_empty_args(self):
        assert normalize_args("read", {}) == {}

    def test_handles_none(self):
        assert normalize_args("read", None) is None


class TestMakeToolCallBlock:
    def test_basic_tool_call_block(self):
        result = make_tool_call_block("call_123", "read", {"filePath": "test.txt"})
        assert result["type"] == "tool-call"
        assert result["toolCallId"] == "call_123"
        assert result["toolName"] == "read"
        # filePath gets mapped to "path" via normalize_input_args
        assert result["input"] == {"path": "test.txt"}

    def test_tool_call_args_remapped(self):
        result = make_tool_call_block("call_456", "write", {"filePath": "f.txt", "oldString": "a", "newString": "b"})
        assert result["input"] == {"path": "f.txt", "old_str": "a", "new_str": "b"}

    def test_empty_args(self):
        result = make_tool_call_block("call_789", "edit", {})
        assert result["input"] == {}


class TestMakeToolResultBlock:
    def test_basic_tool_result_block(self):
        result = make_tool_result_block("call_123", "read", "file content")
        assert result == {
            "type": "tool-result",
            "toolCallId": "call_123",
            "toolName": "read",
            "output": {"type": "text", "value": "file content"},
        }

    def test_empty_value(self):
        result = make_tool_result_block("call_456", "write", "")
        assert result["output"]["value"] == ""


class TestTranslateToolChoice:
    def test_none_returns_none(self):
        assert translate_tool_choice(None) is None

    def test_auto_string(self):
        assert translate_tool_choice("auto") == {"type": "auto"}

    def test_none_string(self):
        assert translate_tool_choice("none") == {"type": "none"}

    def test_required_string(self):
        assert translate_tool_choice("required") == {"type": "any"}

    def test_openai_function_dict(self):
        result = translate_tool_choice({"function": {"name": "my_tool"}})
        assert result == {"type": "tool", "name": "my_tool"}

    def test_responses_function_dict(self):
        result = translate_tool_choice({"type": "function", "name": "my_tool"})
        assert result == {"type": "tool", "name": "my_tool"}

    def test_responses_auto_dict(self):
        result = translate_tool_choice({"type": "auto"})
        assert result == {"type": "auto"}

    def test_unknown_string_falls_back_to_auto(self):
        assert translate_tool_choice("unknown") == {"type": "auto"}

    def test_empty_dict_falls_back_to_auto(self):
        assert translate_tool_choice({}) == {"type": "auto"}
