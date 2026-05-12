from __future__ import annotations

import copy
import json
from functools import lru_cache


SCHEMA_PARAM_MAP = {
    "filePath": "path",
    "oldString": "old_str",
    "newString": "new_str",
}

FILE_TOOLS = {"read", "write", "edit", "readonly"}

ARGS_PATH_MAP = {
    "path": "filePath",
    "file_path": "filePath",
}

ARGS_STR_MAP = {
    "old_str": "oldString",
    "new_str": "newString",
}


def _do_normalize_schema(schema: dict) -> dict:
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return schema
    new_props = {}
    for key, value in properties.items():
        new_key = SCHEMA_PARAM_MAP.get(key, key)
        new_props[new_key] = value
    result = {**schema, "properties": new_props}
    required = schema.get("required")
    if isinstance(required, list):
        result["required"] = [SCHEMA_PARAM_MAP.get(r, r) for r in required]
    return result


@lru_cache(maxsize=128)
def _cached_normalize_schema(schema_json: str) -> dict:
    return _do_normalize_schema(json.loads(schema_json))


def normalize_schema(schema: dict) -> dict:
    if not isinstance(schema, dict):
        return schema
    return copy.deepcopy(_cached_normalize_schema(json.dumps(schema, sort_keys=True)))


def normalize_args(tool_name: str, args: dict, map_path: bool = True) -> dict:
    if not isinstance(args, dict):
        return args
    result = {}
    for k, v in args.items():
        if map_path and tool_name.lower() in FILE_TOOLS:
            k = ARGS_PATH_MAP.get(k, k)
        k = ARGS_STR_MAP.get(k, k)
        result[k] = v
    return result


def normalize_input_args(args: dict) -> dict:
    if not isinstance(args, dict):
        return args
    return {SCHEMA_PARAM_MAP.get(k, k): v for k, v in args.items()}
