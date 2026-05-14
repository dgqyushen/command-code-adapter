from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, field_validator


class ResponseUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    output_tokens_details: dict[str, Any] | None = None
    total_tokens: int = 0


class ResponseOutputText(BaseModel):
    type: Literal["output_text"] = "output_text"
    text: str
    annotations: list = []


class ResponseOutputRefusal(BaseModel):
    type: Literal["refusal"] = "refusal"
    refusal: str


class ResponseOutputMessageContent(BaseModel):
    type: Literal["output_text", "refusal"] = "output_text"
    text: str = ""
    refusal: str = ""
    annotations: list = []


class ResponseOutputMessage(BaseModel):
    type: Literal["message"] = "message"
    id: str
    role: Literal["assistant"] = "assistant"
    status: Literal["completed", "in_progress"] = "completed"
    content: list[dict[str, Any]]


class ResponseReasoningContent(BaseModel):
    type: Literal["reasoning_text"] = "reasoning_text"
    text: str


class ResponseReasoningItem(BaseModel):
    type: Literal["reasoning"] = "reasoning"
    id: str
    content: list[dict[str, Any]]
    status: Literal["completed", "in_progress"] = "completed"


class ResponseFunctionToolCallItem(BaseModel):
    type: Literal["function_call"] = "function_call"
    id: str
    call_id: str
    name: str
    arguments: str
    status: Literal["completed", "in_progress"] = "completed"


class ResponseObject(BaseModel):
    id: str
    object: Literal["response"] = "response"
    status: Literal["completed", "in_progress", "failed", "incomplete"] = "completed"
    created_at: float
    completed_at: float | None = None
    model: str
    output: list[dict[str, Any]]
    usage: ResponseUsage | None = None
    output_text: str = ""


class ResponseCreateRequest(BaseModel):
    model: str
    input: str | list[dict[str, Any]]
    instructions: str | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | dict[str, Any] | None = None
    temperature: float | None = None
    max_output_tokens: int | None = 64000
    top_p: float | None = None
    reasoning: dict[str, Any] | None = None
    previous_response_id: str | None = None
    stream: bool = False
    prompt_cache_retention: str | None = None
    store: bool | None = None
    metadata: dict[str, Any] | None = None
    user: str | None = None
    response_format: dict[str, Any] | None = None
    truncation: str | None = None
    service_tier: str | None = None
    parallel_tool_calls: bool | None = None
    max_tool_calls: int | None = None
    include: list[str] | None = None
    safety_identifier: str | None = None
    prompt_cache_key: str | None = None
    background: bool | None = None
    text: dict[str, Any] | None = None
    top_logprobs: int | None = None
    conversation: str | dict[str, Any] | None = None
    prompt: dict[str, Any] | None = None
    context_management: list[dict[str, Any]] | None = None

    @field_validator("input", mode="before")
    @classmethod
    def coerce_input(cls, v):
        if isinstance(v, str):
            return v
        if isinstance(v, list):
            return v
        return v
