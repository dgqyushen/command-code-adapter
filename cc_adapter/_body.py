from __future__ import annotations

import copy
import datetime
from typing import Any


_CC_BODY_SKELETON: dict[str, Any] = {
    "memory": "",
    "taste": None,
    "skills": None,
    "permissionMode": "standard",
}

_STATIC_CONFIG = {
    "env": "adapter",
    "workingDir": "/home/user/project",
    "environment": "production",
    "structure": ["src/", "tests/", "docs/"],
    "isGitRepo": True,
    "currentBranch": "main",
    "mainBranch": "main",
    "gitStatus": "clean",
    "recentCommits": [],
}


def _make_config(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    base = copy.deepcopy(_STATIC_CONFIG)
    base["date"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    if overrides:
        base.update(overrides)
    return base


def make_cc_body(config: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    return {**_CC_BODY_SKELETON, "config": config, "params": params}
