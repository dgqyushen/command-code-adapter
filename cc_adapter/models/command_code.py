from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class CCTextDelta(BaseModel):
    type: Literal["text-delta"] = "text-delta"
    text: str


class CCReasoningDelta(BaseModel):
    type: Literal["reasoning-delta"] = "reasoning-delta"
    text: str


class CCReasoningEnd(BaseModel):
    type: Literal["reasoning-end"] = "reasoning-end"
    text: str


class CCToolCall(BaseModel):
    type: Literal["tool-call"] = "tool-call"
    toolCallId: str
    toolName: str
    args: dict[str, Any]


class CCToolResult(BaseModel):
    type: Literal["tool-result"] = "tool-result"
    toolCallId: str
    toolName: str
    output: dict[str, Any]
    providerExecuted: bool | None = None


class CCModelUsage(BaseModel):
    inputTokens: int = 0
    outputTokens: int = 0
    inputTokenDetails: dict[str, int] | None = None


class CCFinish(BaseModel):
    type: Literal["finish"] = "finish"
    finishReason: str
    totalUsage: CCModelUsage | None = None


class CCModelError(BaseModel):
    message: str
    statusCode: int | None = None
    isRetryable: bool | None = None


class CCError(BaseModel):
    type: Literal["error"] = "error"
    error: CCModelError


CCEvent = CCTextDelta | CCReasoningDelta | CCReasoningEnd | CCToolCall | CCToolResult | CCFinish | CCError
