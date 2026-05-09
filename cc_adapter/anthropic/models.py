from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class AnthropicMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str | list[dict[str, Any]]


class AnthropicToolChoice(BaseModel):
    type: Literal["auto", "any", "tool"] = "auto"
    name: str | None = None


class AnthropicToolParam(BaseModel):
    name: str
    description: str | None = None
    input_schema: dict[str, Any]


class AnthropicThinkingConfig(BaseModel):
    type: Literal["enabled", "disabled", "adaptive"] = "enabled"
    budget_tokens: int | None = None


class AnthropicRequest(BaseModel):
    model: str
    max_tokens: int = 4096
    messages: list[AnthropicMessage]
    system: str | list[dict[str, Any]] | None = None
    tools: list[AnthropicToolParam] | None = None
    tool_choice: AnthropicToolChoice | None = None
    thinking: AnthropicThinkingConfig | None = None
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    stop_sequences: list[str] | None = None
    metadata: dict[str, Any] | None = None
    stream: bool = False


class AnthropicUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0


class AnthropicResponse(BaseModel):
    id: str
    type: Literal["message"] = "message"
    role: Literal["assistant"] = "assistant"
    content: list[dict[str, Any]]
    model: str
    stop_reason: str | None = None
    stop_sequence: str | None = None
    usage: AnthropicUsage
