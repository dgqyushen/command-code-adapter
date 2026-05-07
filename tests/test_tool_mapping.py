from cc_adapter.translator.tool_mapping import normalize_schema, normalize_args


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
