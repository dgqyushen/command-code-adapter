from __future__ import annotations

import logging
from typing import Any

from cc_adapter.models.openai import ChatCompletionRequest
from cc_adapter.translator.tool_mapping import normalize_schema

logger = logging.getLogger(__name__)

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

NOT_SUPPORTED_PARAMS = {
    "top_p": "top_p",
    "stop": "stop",
    "n": "n",
    "presence_penalty": "presence_penalty",
    "frequency_penalty": "frequency_penalty",
    "user": "user",
    "response_format": "response_format",
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
        import datetime

        return {
            "config": {
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
            },
            "memory": "",
            "taste": None,
            "skills": None,
            "permissionMode": "standard",
            "params": params,
        }

    def _build_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "x-cli-environment": "production",
            "x-project-slug": "adapter",
            "x-internal-team-flag": "false",
            "x-taste-learning": "false",
            "x-command-code-version": "0.25.2-adapter",
        }
