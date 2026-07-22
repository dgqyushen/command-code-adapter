from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

AnthropicMessageRole = Literal["user", "assistant", "system"]


class AnthropicMessage(BaseModel):
    role: AnthropicMessageRole
    content: str | list[dict[str, Any]]


class AnthropicToolChoice(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: Literal["auto", "any", "tool", "none"] = "auto"
    name: str | None = None


class AnthropicToolParam(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    type: str | None = None
    description: str | None = None
    input_schema: dict[str, Any] | None = None


class AnthropicThinkingConfig(BaseModel):
    type: Literal["enabled", "disabled", "adaptive"] = "enabled"
    budget_tokens: int | None = None


class AnthropicRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

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


def extract_system_text(system: str | list[dict[str, Any]] | None) -> str | None:
    if system is None:
        return None
    if isinstance(system, str):
        return system if system.strip() else None
    texts = [
        block.get("text", "")
        for block in system
        if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str)
    ]
    text = " ".join(text for text in texts if text.strip())
    return text if text.strip() else None


def normalize_system_messages(req: AnthropicRequest) -> AnthropicRequest:
    system_parts = []
    top_level_system = extract_system_text(req.system)
    if top_level_system:
        system_parts.append(top_level_system)

    messages = []
    found_message_system = False
    for message in req.messages:
        if message.role == "system":
            found_message_system = True
            message_system = extract_system_text(message.content)
            if message_system:
                system_parts.append(message_system)
            continue
        messages.append(message)

    if not found_message_system:
        return req

    return req.model_copy(
        update={
            "messages": messages,
            "system": "\n\n".join(system_parts) if system_parts else None,
        }
    )
