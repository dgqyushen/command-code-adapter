from __future__ import annotations

import logging
from typing import Any

from cc_adapter.models.openai import ChatCompletionRequest

logger = logging.getLogger(__name__)

NOT_SUPPORTED_PARAMS = {
    "top_p": "top_p",
    "stop": "stop",
    "n": "n",
    "presence_penalty": "presence_penalty",
    "frequency_penalty": "frequency_penalty",
    "user": "user",
    "response_format": "response_format",
    "tool_choice": "tool_choice",
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

    def _split_messages(self, messages):
        system_prompt = None
        others = []
        for msg in messages:
            if msg.role == "system":
                system_prompt = msg.content
            else:
                d = {"role": msg.role, "content": msg.content}
                if msg.tool_calls:
                    d["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": tc.type,
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        for tc in msg.tool_calls
                    ]
                if msg.tool_call_id:
                    d["tool_call_id"] = msg.tool_call_id
                if msg.name:
                    d["name"] = msg.name
                others.append(d)
        return system_prompt, others

    def _build_body(self, req: ChatCompletionRequest, system_prompt: str | None, messages: list) -> dict:
        params: dict[str, Any] = {
            "model": req.model,
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
                    "parameters": t.function.parameters or {},
                }
                for t in req.tools
            ]
        return {
            "config": {"env": "adapter"},
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
