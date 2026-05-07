from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class FunctionDefinition(BaseModel):
    name: str
    description: str | None = None
    parameters: dict[str, Any] | None = None


class FunctionCall(BaseModel):
    name: str
    arguments: str


class ToolDefinition(BaseModel):
    type: Literal["function"] = "function"
    function: FunctionDefinition


class ToolCall(BaseModel):
    id: str
    type: Literal["function"] = "function"
    function: FunctionCall


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None
    name: str | None = None


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    tools: list[ToolDefinition] | None = None
    tool_choice: Literal["auto", "none", "required"] | dict[str, Any] | None = None
    max_tokens: int | None = 64000
    temperature: float | None = None
    top_p: float | None = None
    stream: bool = False
    stop: str | list[str] | None = None
    presence_penalty: float | None = None
    frequency_penalty: float | None = None
    n: int | None = None
    user: str | None = None
    response_format: dict[str, Any] | None = None


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatMessageResponse(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: str | None = None
    reasoning_content: str | None = None
    tool_calls: list[ToolCall] | None = None


class Choice(BaseModel):
    index: int = 0
    message: ChatMessageResponse
    finish_reason: Literal["stop", "length", "tool_calls", "content_filter"] | None = None


class ChatCompletionResponse(BaseModel):
    id: str
    object: Literal["chat.completion"] = "chat.completion"
    created: int
    model: str
    choices: list[Choice]
    usage: Usage | None = None


class DeltaChoice(BaseModel):
    index: int = 0
    delta: ChatMessageResponse
    finish_reason: Literal["stop", "length", "tool_calls", "content_filter"] | None = None


class ChatCompletionChunk(BaseModel):
    id: str
    object: Literal["chat.completion.chunk"] = "chat.completion.chunk"
    created: int
    model: str
    choices: list[DeltaChoice]
    usage: Usage | None = None
