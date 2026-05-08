from __future__ import annotations

import datetime
import logging
from typing import Any

from cc_adapter.models.openai import ChatCompletionRequest
from cc_adapter.translator.tool_mapping import normalize_schema

logger = logging.getLogger(__name__)

REASONING_EFFORT_MAX = (
    "Reasoning Effort: Absolute maximum with no shortcuts permitted.\n"
    "You MUST be very thorough in your thinking and comprehensively decompose "
    "the problem to resolve the root cause, rigorously stress-testing your "
    "logic against all potential paths, edge cases, and adversarial scenarios.\n"
    "Explicitly write out your entire deliberation process, documenting every "
    "intermediate step, considered alternative, and rejected hypothesis to "
    "ensure absolutely no assumption is left unchecked.\n\n"
)

MODEL_PROVIDER_MAP: dict[str, str] = {
    "deepseek-v4-pro": "deepseek",
    "deepseek-v4-flash": "deepseek",
    "kimi-k2-6": "kimi",
    "kimi-k2-5": "kimi",
    "glm-5-1": "glm",
    "glm-5": "glm",
    "minimax-m2-7": "minimax",
    "minimax-m2-5": "minimax",
    "qwen-3-6-max-preview": "qwen",
    "qwen-3-6-plus": "qwen",
    "step-3-5-flash": "step",
}

REASONING_EFFORT_MAP: dict[str, str] = {
    "off": "Respond directly without showing step-by-step reasoning.",
    "low": "Be concise. Minimize step-by-step reasoning.",
    "medium": "",
    "high": "Think step-by-step and show your reasoning process.",
    "xhigh": "Think carefully step-by-step. Show detailed reasoning.",
    "max": "Think very thoroughly. Show exhaustive step-by-step reasoning with detailed analysis.",
}

NOT_SUPPORTED_PARAMS = {
    "top_p": "top_p",
    "stop": "stop",
    "n": "n",
    "presence_penalty": "presence_penalty",
    "frequency_penalty": "frequency_penalty",
    "user": "user",
    "response_format": "response_format",
}

_CC_BODY_SKELETON: dict[str, Any] = {
    "memory": "",
    "taste": None,
    "skills": None,
    "permissionMode": "standard",
}


def _make_config(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    base = {
        "env": "adapter",
        "workingDir": "/home/user/project",
        "date": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "environment": "production",
        "structure": ["src/", "tests/", "docs/"],
        "isGitRepo": True,
        "currentBranch": "main",
        "mainBranch": "main",
        "gitStatus": "clean",
        "recentCommits": [],
    }
    if overrides:
        base.update(overrides)
    return base


def make_cc_body(config: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    return {**_CC_BODY_SKELETON, "config": config, "params": params}


def make_cc_headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "x-cli-environment": "production",
        "x-project-slug": "adapter",
        "x-internal-team-flag": "false",
        "x-taste-learning": "false",
        "x-command-code-version": "0.25.2-adapter",
    }


class RequestTranslator:
    def translate(self, req: ChatCompletionRequest) -> tuple[dict[str, Any], dict[str, Any]]:
        self._warn_unsupported(req)
        system_prompt, messages = self._split_messages(req.messages)
        cc_body = self._build_body(req, system_prompt, messages)
        cc_headers = self._build_headers()
        return cc_body, cc_headers

    def _warn_unsupported(self, req: ChatCompletionRequest) -> None:
        for attr, name in NOT_SUPPORTED_PARAMS.items():
            value = getattr(req, attr, None)
            if value is not None:
                logger.warning("Unsupported parameter ignored: %s = %s", name, value)

    @staticmethod
    def _translate_tool_choice(tool_choice: Any) -> dict[str, Any] | None:
        if tool_choice is None:
            return None
        if isinstance(tool_choice, str):
            if tool_choice == "auto":
                return {"type": "auto"}
            elif tool_choice == "none":
                return {"type": "none"}
            elif tool_choice == "required":
                return {"type": "any"}
        if isinstance(tool_choice, dict):
            name = (tool_choice.get("function") or {}).get("name")
            if name:
                return {"type": "tool", "name": name}
        return {"type": "auto"}

    @staticmethod
    def _wrap_content(content: str | None) -> list[dict[str, Any]]:
        return [{"type": "text", "text": content or ""}]

    def _split_messages(self, messages):
        system_prompt = None
        others = []
        for msg in messages:
            if msg.role == "system":
                system_prompt = msg.content
            elif msg.role == "tool":
                d: dict[str, Any] = {
                    "role": "user",
                    "content": self._wrap_content(msg.content),
                }
                if msg.tool_call_id:
                    d["tool_call_id"] = msg.tool_call_id
                others.append(d)
            else:
                d = {"role": msg.role, "content": self._wrap_content(msg.content)}
                if msg.tool_calls:
                    d["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": tc.type,
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        for tc in msg.tool_calls
                    ]
                if msg.name:
                    d["name"] = msg.name
                others.append(d)
        return system_prompt, others

    @staticmethod
    def _normalize_model(model: str) -> str:
        if "/" in model:
            return model
        prefix = MODEL_PROVIDER_MAP.get(model)
        if prefix:
            return f"{prefix}/{model}"
        return model

    @staticmethod
    def _is_deepseek_v4(model: str) -> bool:
        bare = model.split("/")[-1]
        return bare.startswith("deepseek-v4")

    def _build_body(self, req: ChatCompletionRequest, system_prompt: str | None, messages: list) -> dict:
        params: dict[str, Any] = {
            "model": self._normalize_model(req.model),
            "messages": messages,
            "max_tokens": req.max_tokens or 64000,
            "stream": req.stream,
        }
        if system_prompt:
            params["system"] = system_prompt
        if req.temperature is not None:
            params["temperature"] = req.temperature
        if req.reasoning_effort is not None:
            effort = req.reasoning_effort
            if self._is_deepseek_v4(req.model) and effort in ("xhigh", "max"):
                params["reasoning_effort"] = "max"
                if system_prompt:
                    params["system"] = f"{REASONING_EFFORT_MAX}{system_prompt}"
                else:
                    params["system"] = REASONING_EFFORT_MAX
            else:
                params["reasoning_effort"] = effort
                instruction = REASONING_EFFORT_MAP.get(effort, "")
                if instruction:
                    if system_prompt:
                        params["system"] = f"{system_prompt}\n{instruction}"
                    else:
                        params["system"] = instruction
        if req.tools:
            params["tools"] = [
                {
                    "name": t.function.name,
                    "description": t.function.description,
                    "input_schema": normalize_schema(t.function.parameters or {}),
                }
                for t in req.tools
            ]
            tool_choice = self._translate_tool_choice(req.tool_choice)
            if tool_choice is not None:
                params["tool_choice"] = tool_choice
        return make_cc_body(config=_make_config(), params=params)

    def _build_headers(self) -> dict[str, str]:
        return make_cc_headers()
