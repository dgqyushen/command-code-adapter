from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class ResponseUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    output_tokens_details: dict[str, Any] | None = None
    total_tokens: int = 0


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
