# Command Code OpenAI Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an HTTP adapter that exposes Command Code API through OpenAI Chat Completions format (`POST /v1/chat/completions`).

**Architecture:** FastAPI server receives OpenAI-format requests, translates them to Command Code `/alpha/generate` format via layered translators, sends via httpx, and translates the SSE stream back to OpenAI format in real-time.

**Tech Stack:** Python 3.11+, FastAPI, httpx, pydantic, pydantic-settings, pytest

---

## File Structure

```
cc_adapter/
├── __init__.py
├── main.py                  # FastAPI app, routes, SSE streaming
├── config.py                # pydantic-settings AppConfig
├── models/
│   ├── __init__.py
│   ├── openai.py            # OpenAI ChatCompletion request/response Pydantic models
│   └── command_code.py      # CC SSE event Pydantic models
├── translator/
│   ├── __init__.py
│   ├── request.py           # OpenAI → CC request translation
│   └── response.py          # CC SSE → OpenAI response translation
├── client.py                # httpx wrapper for CC API
└── errors.py                # exception classes + error mapping

tests/
├── __init__.py
├── test_request_translator.py
├── test_response_translator.py
└── test_integration.py
```

---

### Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `cc_adapter/__init__.py`
- Create: `tests/__init__.py`
- Create: `cc_adapter/config.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[tool.poetry]
name = "cc-adapter"
version = "0.1.0"
description = "OpenAI Chat Completions adapter for Command Code API"
authors = ["Command Code Adapter"]
packages = [{ include = "cc_adapter" }]

[tool.poetry.dependencies]
python = ">=3.11"
fastapi = "^0.115.0"
httpx = "^0.28.0"
pydantic = "^2.0"
pydantic-settings = "^2.0"
uvicorn = { version = "^0.34.0", extras = ["standard"] }

[tool.poetry.group.dev.dependencies]
pytest = "^8.0"
pytest-asyncio = "^0.25.0"
httpx = "^0.28.0"

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"
```

- [ ] **Step 2: Run poetry install**

Run: `cd ~/codes/command-code-adapter && poetry install`
Expected: Success, virtualenv created

- [ ] **Step 3: Create .env.example**

```
CC_API_KEY=user_your_key_here
CC_BASE_URL=https://api.commandcode.ai
CC_ADAPTER_HOST=0.0.0.0
CC_ADAPTER_PORT=8080
CC_ADAPTER_LOG_LEVEL=INFO
```

- [ ] **Step 4: Create empty __init__.py files**

Run:
```bash
touch cc_adapter/__init__.py tests/__init__.py
```

- [ ] **Step 5: Create config.py**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CC_ADAPTER_", env_file=".env", extra="ignore")

    host: str = "0.0.0.0"
    port: int = 8080
    log_level: str = "INFO"

    cc_api_key: str = ""
    cc_base_url: str = "https://api.commandcode.ai"
```

- [ ] **Step 6: Commit**

```bash
git -C ~/codes/command-code-adapter init
git -C ~/codes/command-code-adapter add pyproject.toml .env.example cc_adapter/ tests/
git -C ~/codes/command-code-adapter commit -m "chore: scaffold project with poetry and config"
```

---

### Task 2: OpenAI Pydantic Models

**Files:**
- Create: `cc_adapter/models/__init__.py`
- Create: `cc_adapter/models/openai.py`

- [ ] **Step 1: Write openai.py models**

```python
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class FunctionDefinition(BaseModel):
    name: str
    description: str | None = None
    parameters: dict[str, Any] | None = None


class ToolDefinition(BaseModel):
    type: Literal["function"] = "function"
    function: FunctionDefinition


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None
    name: str | None = None


class ToolCall(BaseModel):
    id: str
    type: Literal["function"] = "function"
    function: FunctionCall


class FunctionCall(BaseModel):
    name: str
    arguments: str


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
```

- [ ] **Step 2: Create models/__init__.py**

```python
from .openai import (
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    ChatMessageResponse,
    Choice,
    DeltaChoice,
    FunctionCall,
    FunctionDefinition,
    ToolCall,
    ToolDefinition,
    Usage,
)

__all__ = [
    "ChatCompletionChunk",
    "ChatCompletionRequest",
    "ChatCompletionResponse",
    "ChatMessage",
    "ChatMessageResponse",
    "Choice",
    "DeltaChoice",
    "FunctionCall",
    "FunctionDefinition",
    "ToolCall",
    "ToolDefinition",
    "Usage",
]
```

- [ ] **Step 3: Write failing test — verify model creation works**

Create `tests/test_request_translator.py`:

```python
import pytest
from cc_adapter.models.openai import ChatCompletionRequest


def test_request_model_creation():
    req = ChatCompletionRequest(
        model="claude-sonnet-4-6",
        messages=[{"role": "user", "content": "hello"}],
        stream=False,
    )
    assert req.model == "claude-sonnet-4-6"
    assert len(req.messages) == 1
    assert req.messages[0].content == "hello"
    assert req.stream is False
```

- [ ] **Step 4: Run test to verify pass**

Run: `cd ~/codes/command-code-adapter && poetry run pytest tests/test_request_translator.py::test_request_model_creation -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git -C ~/codes/command-code-adapter add cc_adapter/models/ tests/
git -C ~/codes/command-code-adapter commit -m "feat: add OpenAI request/response pydantic models"
```

---

### Task 3: Command Code Event Models

**Files:**
- Create: `cc_adapter/models/command_code.py`

- [ ] **Step 1: Write command_code.py models**

```python
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


class CCFinish(BaseModel):
    type: Literal["finish"] = "finish"
    finishReason: str
    totalUsage: CCModelUsage | None = None


class CCModelUsage(BaseModel):
    inputTokens: int = 0
    outputTokens: int = 0
    inputTokenDetails: dict[str, int] | None = None


class CCError(BaseModel):
    type: Literal["error"] = "error"
    error: CCModelError


class CCModelError(BaseModel):
    message: str
    statusCode: int | None = None
    isRetryable: bool | None = None


CCEvent = CCTextDelta | CCReasoningDelta | CCReasoningEnd | CCToolCall | CCToolResult | CCFinish | CCError
```

- [ ] **Step 2: Update models/__init__.py**

```python
from .command_code import (
    CCEvent,
    CCFinish,
    CCTextDelta,
    CCToolCall,
    CCToolResult,
    CCModelUsage,
    CCReasoningDelta,
    CCReasoningEnd,
    CCError,
)
from .openai import (
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    ChatMessageResponse,
    Choice,
    DeltaChoice,
    FunctionCall,
    FunctionDefinition,
    ToolCall,
    ToolDefinition,
    Usage,
)

__all__ = [
    "CCEvent",
    "CCFinish",
    "CCTextDelta",
    "CCToolCall",
    "CCToolResult",
    "CCModelUsage",
    "CCReasoningDelta",
    "CCReasoningEnd",
    "CCError",
    "ChatCompletionChunk",
    "ChatCompletionRequest",
    "ChatCompletionResponse",
    "ChatMessage",
    "ChatMessageResponse",
    "Choice",
    "DeltaChoice",
    "FunctionCall",
    "FunctionDefinition",
    "ToolCall",
    "ToolDefinition",
    "Usage",
]
```

- [ ] **Step 3: Run tests to ensure models work**

Run: `cd ~/codes/command-code-adapter && poetry run python -c "from cc_adapter.models.command_code import CCTextDelta; m = CCTextDelta(text='hi'); print(m.model_dump_json())"`
Expected: `{"type":"text-delta","text":"hi"}`

- [ ] **Step 4: Commit**

```bash
git -C ~/codes/command-code-adapter add cc_adapter/models/
git -C ~/codes/command-code-adapter commit -m "feat: add Command Code SSE event models"
```

---

### Task 4: Error Handling Module

**Files:**
- Create: `cc_adapter/errors.py`

- [ ] **Step 1: Write errors.py**

```python
from __future__ import annotations


class AdapterError(Exception):
    def __init__(self, message: str, status_code: int = 500, original_status: int | None = None):
        self.message = message
        self.status_code = status_code
        self.original_status = original_status
        super().__init__(self.message)

    def to_openai_error(self) -> dict:
        error_type_map = {
            401: "authentication_error",
            403: "authentication_error",
            404: "not_found",
            429: "rate_limit_error",
            400: "invalid_request_error",
            502: "api_error",
            504: "timeout_error",
        }
        error_type = error_type_map.get(self.original_status or self.status_code, "api_error")
        return {
            "error": {
                "message": self.message,
                "type": error_type,
                "code": self.original_status or self.status_code,
            }
        }


class AuthenticationError(AdapterError):
    def __init__(self, message: str = "Authentication failed", original_status: int | None = 401):
        super().__init__(message=message, status_code=401, original_status=original_status)


class RateLimitError(AdapterError):
    def __init__(self, message: str = "Rate limit exceeded", original_status: int | None = 429):
        super().__init__(message=message, status_code=429, original_status=original_status)


class UpstreamError(AdapterError):
    def __init__(self, message: str = "Upstream server error", original_status: int | None = 502):
        super().__init__(message=message, status_code=502, original_status=original_status)


class TimeoutError_(AdapterError):
    def __init__(self, message: str = "Request timed out", original_status: int | None = 504):
        super().__init__(message=message, status_code=504, original_status=original_status)


def map_upstream_error(status_code: int, message: str) -> AdapterError:
    if status_code == 401 or status_code == 403:
        return AuthenticationError(message=message, original_status=status_code)
    elif status_code == 429:
        return RateLimitError(message=message, original_status=status_code)
    elif status_code >= 500:
        return UpstreamError(message=message, original_status=status_code)
    elif status_code == 400 or status_code == 404:
        return AdapterError(message=message, status_code=status_code, original_status=status_code)
    return AdapterError(message=message, status_code=502, original_status=status_code)
```

- [ ] **Step 2: Write failing test**

Update `tests/test_request_translator.py`:

```python
from cc_adapter.errors import map_upstream_error, AuthenticationError, RateLimitError


def test_map_401_to_authentication_error():
    err = map_upstream_error(401, "Unauthorized")
    assert isinstance(err, AuthenticationError)
    assert err.status_code == 401
    assert err.to_openai_error()["error"]["type"] == "authentication_error"


def test_map_429_to_rate_limit_error():
    err = map_upstream_error(429, "Too Many Requests")
    assert isinstance(err, RateLimitError)
    assert err.to_openai_error()["error"]["type"] == "rate_limit_error"
```

- [ ] **Step 3: Run test**

Run: `cd ~/codes/command-code-adapter && poetry run pytest tests/test_request_translator.py -v`
Expected: Both tests PASS

- [ ] **Step 4: Commit**

```bash
git -C ~/codes/command-code-adapter add cc_adapter/errors.py tests/
git -C ~/codes/command-code-adapter commit -m "feat: add error handling with OpenAI-compatible error format"
```

---

### Task 5: Request Translator

**Files:**
- Create: `cc_adapter/translator/__init__.py`
- Create: `cc_adapter/translator/request.py`

- [ ] **Step 1: Write translator/request.py**

```python
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
```

- [ ] **Step 2: Write failing test**

```python
import pytest
from cc_adapter.translator.request import RequestTranslator
from cc_adapter.models.openai import ChatCompletionRequest, ChatMessage, ToolDefinition, FunctionDefinition


@pytest.fixture
def translator():
    return RequestTranslator()


def test_basic_message_translation(translator):
    req = ChatCompletionRequest(
        model="claude-sonnet-4-6",
        messages=[ChatMessage(role="user", content="hello")],
    )
    body, headers = translator.translate(req)
    assert body["params"]["model"] == "claude-sonnet-4-6"
    assert body["params"]["messages"][0]["content"] == "hello"
    assert body["params"]["stream"] is False
    assert body["config"]["env"] == "adapter"
    assert "Authorization" not in headers


def test_system_prompt_extraction(translator):
    req = ChatCompletionRequest(
        model="gpt-5.4",
        messages=[
            ChatMessage(role="system", content="You are a helpful assistant."),
            ChatMessage(role="user", content="hi"),
        ],
    )
    body, _ = translator.translate(req)
    assert body["params"]["system"] == "You are a helpful assistant."
    assert len(body["params"]["messages"]) == 1
    assert body["params"]["messages"][0]["role"] == "user"


def test_tool_translation(translator):
    req = ChatCompletionRequest(
        model="claude-sonnet-4-6",
        messages=[ChatMessage(role="user", content="list files")],
        tools=[
            ToolDefinition(
                function=FunctionDefinition(
                    name="read_file",
                    description="Read a file",
                    parameters={"type": "object", "properties": {"path": {"type": "string"}}},
                )
            )
        ],
    )
    body, _ = translator.translate(req)
    assert len(body["params"]["tools"]) == 1
    assert body["params"]["tools"][0]["name"] == "read_file"


def test_stream_true_passed_through(translator):
    req = ChatCompletionRequest(
        model="claude-sonnet-4-6",
        messages=[ChatMessage(role="user", content="hi")],
        stream=True,
    )
    body, _ = translator.translate(req)
    assert body["params"]["stream"] is True
```

- [ ] **Step 3: Run test**

Run: `cd ~/codes/command-code-adapter && poetry run pytest tests/test_request_translator.py -v`
Expected: All 4 tests PASS

- [ ] **Step 4: Commit**

```bash
git -C ~/codes/command-code-adapter add cc_adapter/translator/ tests/
git -C ~/codes/command-code-adapter commit -m "feat: add request translator (OpenAI -> Command Code)"
```

---

### Task 6: Response Translator

**Files:**
- Create: `cc_adapter/translator/response.py`

- [ ] **Step 1: Write translator/response.py**

```python
from __future__ import annotations

import json
import logging
import uuid
import time
from typing import AsyncGenerator

from cc_adapter.models.openai import ChatCompletionResponse, ChatCompletionChunk, ChatMessageResponse, Choice, DeltaChoice, ToolCall, FunctionCall, Usage

logger = logging.getLogger(__name__)

FINISH_REASON_MAP = {
    "end_turn": "stop",
    "tool_calls": "tool_calls",
}


def _generate_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex[:12]}"


def _now() -> int:
    return int(time.time())


def _map_finish_reason(cc_reason: str | None) -> str | None:
    if cc_reason is None:
        return None
    return FINISH_REASON_MAP.get(cc_reason, "stop")


def _make_tool_call(cc_event: dict, index: int = 0) -> ToolCall:
    return ToolCall(
        id=cc_event.get("toolCallId", f"call_{uuid.uuid4().hex[:8]}"),
        function=FunctionCall(
            name=cc_event.get("toolName", ""),
            arguments=json.dumps(cc_event.get("args", {})),
        ),
    )


async def translate_stream(cc_stream: AsyncGenerator[dict, None], model: str) -> AsyncGenerator[str, None]:
    """Translate CC SSE events into OpenAI SSE chunks on the fly."""
    response_id = _generate_id()
    created = _now()
    tool_call_index = 0
    usage = None

    async for event in cc_stream:
        event_type = event.get("type")

        if event_type == "text-delta":
            chunk = ChatCompletionChunk(
                id=response_id,
                created=created,
                model=model,
                choices=[DeltaChoice(delta=ChatMessageResponse(content=event.get("text", "")))],
            )
            yield f"data: {chunk.model_dump_json(exclude_none=True)}\n\n"

        elif event_type == "reasoning-delta":
            logger.debug("Reasoning delta ignored: %s", event.get("text", "")[:50])

        elif event_type == "tool-call":
            tool_call = _make_tool_call(event, tool_call_index)
            chunk = ChatCompletionChunk(
                id=response_id,
                created=created,
                model=model,
                choices=[DeltaChoice(delta=ChatMessageResponse(tool_calls=[tool_call]))],
            )
            yield f"data: {chunk.model_dump_json(exclude_none=True)}\n\n"
            tool_call_index += 1

        elif event_type == "tool-result":
            pass  # OpenAI doesn't return tool results in chat completions

        elif event_type == "finish":
            finish_reason = _map_finish_reason(event.get("finishReason"))
            raw_usage = event.get("totalUsage")
            if raw_usage:
                usage = Usage(
                    prompt_tokens=raw_usage.get("inputTokens", 0),
                    completion_tokens=raw_usage.get("outputTokens", 0),
                    total_tokens=raw_usage.get("inputTokens", 0) + raw_usage.get("outputTokens", 0),
                )
            chunk = ChatCompletionChunk(
                id=response_id,
                created=created,
                model=model,
                choices=[DeltaChoice(delta=ChatMessageResponse(), finish_reason=finish_reason)],
                usage=usage,
            )
            yield f"data: {chunk.model_dump_json(exclude_none=True)}\n\n"

        elif event_type == "error":
            err_data = event.get("error", {})
            logger.error("CC stream error: %s", err_data.get("message", "Unknown"))
            chunk = ChatCompletionChunk(
                id=response_id,
                created=created,
                model=model,
                choices=[DeltaChoice(delta=ChatMessageResponse(), finish_reason="stop")],
            )
            yield f"data: {chunk.model_dump_json(exclude_none=True)}\n\n"

    yield "data: [DONE]\n\n"


async def collect_and_translate_nonstream(cc_stream: AsyncGenerator[dict, None], model: str) -> ChatCompletionResponse:
    """Collect all CC SSE events and build a single ChatCompletionResponse."""
    response_id = _generate_id()
    created = _now()
    content_parts: list[str] = []
    tool_calls: list[ToolCall] = []
    finish_reason: str | None = None
    usage: Usage | None = None
    tool_call_index = 0

    async for event in cc_stream:
        event_type = event.get("type")

        if event_type == "text-delta":
            content_parts.append(event.get("text", ""))

        elif event_type == "tool-call":
            tool_calls.append(_make_tool_call(event, tool_call_index))
            tool_call_index += 1

        elif event_type == "finish":
            finish_reason = _map_finish_reason(event.get("finishReason"))
            raw_usage = event.get("totalUsage")
            if raw_usage:
                usage = Usage(
                    prompt_tokens=raw_usage.get("inputTokens", 0),
                    completion_tokens=raw_usage.get("outputTokens", 0),
                    total_tokens=raw_usage.get("inputTokens", 0) + raw_usage.get("outputTokens", 0),
                )

        elif event_type == "error":
            err_data = event.get("error", {})
            logger.error("CC stream error: %s", err_data.get("message", "Unknown"))
            finish_reason = "stop"

    content = "".join(content_parts) or None
    message = ChatMessageResponse(content=content, tool_calls=tool_calls or None)
    choice = Choice(message=message, finish_reason=finish_reason or "stop")

    return ChatCompletionResponse(
        id=response_id,
        created=created,
        model=model,
        choices=[choice],
        usage=usage,
    )
```

- [ ] **Step 2: Write failing test for non-stream response**

```python
import pytest
from cc_adapter.translator.response import collect_and_translate_nonstream


@pytest.mark.asyncio
async def test_nonstream_simple_text():
    async def fake_stream():
        yield {"type": "text-delta", "text": "Hello"}
        yield {"type": "text-delta", "text": " world"}
        yield {"type": "finish", "finishReason": "end_turn", "totalUsage": {"inputTokens": 10, "outputTokens": 5}}

    result = await collect_and_translate_nonstream(fake_stream(), "claude-sonnet-4-6")
    assert result.choices[0].message.content == "Hello world"
    assert result.choices[0].finish_reason == "stop"
    assert result.usage.prompt_tokens == 10
    assert result.usage.completion_tokens == 5


@pytest.mark.asyncio
async def test_nonstream_tool_calls():
    async def fake_stream():
        yield {"type": "tool-call", "toolCallId": "call_1", "toolName": "read_file", "args": {"path": "/tmp/x"}}
        yield {"type": "finish", "finishReason": "tool_calls", "totalUsage": {"inputTokens": 5, "outputTokens": 2}}

    result = await collect_and_translate_nonstream(fake_stream(), "gpt-5.4")
    assert len(result.choices[0].message.tool_calls) == 1
    assert result.choices[0].message.tool_calls[0].function.name == "read_file"
    assert result.choices[0].finish_reason == "tool_calls"
```

- [ ] **Step 3: Write failing test for stream response**

```python
import pytest
from cc_adapter.translator.response import translate_stream


@pytest.mark.asyncio
async def test_stream_output():
    async def fake_stream():
        yield {"type": "text-delta", "text": "Hi"}
        yield {"type": "finish", "finishReason": "end_turn", "totalUsage": {"inputTokens": 1, "outputTokens": 1}}

    chunks = []
    async for chunk in translate_stream(fake_stream(), "claude-sonnet-4-6"):
        chunks.append(chunk)

    assert len(chunks) == 3  # text-delta + finish + [DONE]
    assert 'data: {"id":"chatcmpl-' in chunks[0]
    assert '"content":"Hi"' in chunks[0]
    assert chunks[2] == "data: [DONE]\n\n"
```

- [ ] **Step 4: Run tests**

Run: `cd ~/codes/command-code-adapter && poetry run pytest tests/test_response_translator.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git -C ~/codes/command-code-adapter add cc_adapter/translator/ tests/
git -C ~/codes/command-code-adapter commit -m "feat: add response translator (Command Code SSE -> OpenAI)"
```

---

### Task 7: HTTP Client for Command Code API

**Files:**
- Create: `cc_adapter/client.py`

- [ ] **Step 1: Write client.py**

```python
from __future__ import annotations

import logging
from typing import AsyncGenerator, Any

import httpx

from cc_adapter.errors import map_upstream_error, AuthenticationError

logger = logging.getLogger(__name__)


class CommandCodeClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    async def generate(
        self, body: dict[str, Any], extra_headers: dict[str, str] | None = None
    ) -> AsyncGenerator[dict[str, Any], None]:
        if not self.api_key:
            raise AuthenticationError("CC_API_KEY is not configured")

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            **(extra_headers or {}),
        }

        url = f"{self.base_url}/alpha/generate"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                async with client.stream("POST", url, json=body, headers=headers) as response:
                    if response.is_error:
                        error_body = await response.aread()
                        text = error_body.decode() if error_body else response.reason_phrase or "Unknown error"
                        raise map_upstream_error(response.status_code, text)

                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            yield __import__("json").loads(line)
                        except (ValueError, KeyError) as e:
                            logger.warning("Failed to parse CC event: %s", e)

            except httpx.TimeoutException:
                from cc_adapter.errors import TimeoutError_
                raise TimeoutError_("Command Code API request timed out")
            except httpx.HTTPStatusError as e:
                raise map_upstream_error(e.response.status_code, str(e))
```

- [ ] **Step 2: Write failing test**

Create `tests/test_client.py`:

```python
import pytest
from cc_adapter.client import CommandCodeClient
from cc_adapter.errors import AuthenticationError


@pytest.mark.asyncio
async def test_client_requires_api_key():
    client = CommandCodeClient(base_url="https://api.commandcode.ai", api_key="")
    with pytest.raises(AuthenticationError, match="CC_API_KEY is not configured"):
        async for _ in client.generate({"params": {"model": "test", "messages": []}}):
            pass
```

- [ ] **Step 3: Run test**

Run: `cd ~/codes/command-code-adapter && poetry run pytest tests/test_client.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git -C ~/codes/command-code-adapter add cc_adapter/client.py tests/test_client.py
git -C ~/codes/command-code-adapter commit -m "feat: add httpx-based Command Code API client"
```

---

### Task 8: FastAPI Application and Routes

**Files:**
- Create: `cc_adapter/main.py`

- [ ] **Step 1: Write main.py**

```python
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from cc_adapter.config import AppConfig
from cc_adapter.client import CommandCodeClient
from cc_adapter.translator.request import RequestTranslator
from cc_adapter.translator.response import translate_stream, collect_and_translate_nonstream
from cc_adapter.errors import AdapterError
from cc_adapter.models.openai import ChatCompletionRequest

logger = logging.getLogger(__name__)
config = AppConfig()
cc_client = CommandCodeClient(base_url=config.cc_base_url, api_key=config.cc_api_key)
request_translator = RequestTranslator()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=getattr(logging, config.log_level.upper(), logging.INFO))
    logger.info("CC Adapter starting — CC API: %s", config.cc_base_url)
    if not config.cc_api_key:
        logger.warning("CC_API_KEY is not set. Set it via environment variable or .env file.")
    yield


app = FastAPI(title="Command Code Adapter", version="0.1.0", lifespan=lifespan)


@app.exception_handler(AdapterError)
async def adapter_error_handler(request: Request, exc: AdapterError):
    return JSONResponse(status_code=exc.status_code, content=exc.to_openai_error())


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest):
    logger.info("Request: model=%s stream=%s messages=%d tools=%s",
                req.model, req.stream, len(req.messages), "yes" if req.tools else "no")

    cc_body, cc_headers = request_translator.translate(req)
    cc_body["params"]["stream"] = True  # always stream from CC internally

    try:
        cc_stream = cc_client.generate(cc_body, cc_headers)
    except AdapterError:
        raise
    except Exception as e:
        logger.exception("Unexpected error calling CC API")
        raise AdapterError(message=str(e), status_code=502)

    if req.stream:
        return StreamingResponse(
            translate_stream(cc_stream, req.model),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    else:
        result = await collect_and_translate_nonstream(cc_stream, req.model)
        return result


def run():
    import uvicorn
    uvicorn.run(
        "cc_adapter.main:app",
        host=config.host,
        port=config.port,
        log_level=config.log_level.lower(),
    )
```

- [ ] **Step 2: Create __main__.py for `python -m cc_adapter`**

Create `cc_adapter/__main__.py`:

```python
from cc_adapter.main import run

if __name__ == "__main__":
    run()
```

- [ ] **Step 3: Add [project.scripts] to pyproject.toml**

Add to `pyproject.toml`:

```toml
[tool.poetry.scripts]
cc-adapter = "cc_adapter.main:run"
```

- [ ] **Step 4: Run the app and test with curl (manual test)**

```bash
cd ~/codes/command-code-adapter
CC_API_KEY=user_your_key_here poetry run python -m cc_adapter
```

Expected: Uvicorn starts on 0.0.0.0:8080

In another terminal:

```bash
# Non-streaming
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-sonnet-4-6","messages":[{"role":"user","content":"hello"}],"stream":false}'

# Streaming
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-sonnet-4-6","messages":[{"role":"user","content":"hello"}],"stream":true}'

# Health check
curl http://localhost:8080/health
```

- [ ] **Step 5: Commit**

```bash
git -C ~/codes/command-code-adapter add cc_adapter/main.py cc_adapter/__main__.py pyproject.toml
git -C ~/codes/command-code-adapter commit -m "feat: add FastAPI application with /v1/chat/completions route"
```

---

### Task 9: Integration Tests

**Files:**
- Create: `tests/test_integration.py`

- [ ] **Step 1: Write integration test**

```python
import pytest
from httpx import AsyncClient, ASGITransport
from cc_adapter.main import app


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_health_endpoint(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_nonstream_unsupported_params_logged(client):
    """Request with unsupported params should not error."""
    payload = {
        "model": "claude-sonnet-4-6",
        "messages": [{"role": "user", "content": "hi"}],
        "top_p": 0.9,
        "stream": False,
    }
    # This will likely return 502 because CC_API_KEY is not set in test,
    # but it should NOT crash — it should go through the translator
    response = await client.post("/v1/chat/completions", json=payload)
    assert response.status_code in (200, 401, 502)


@pytest.mark.asyncio
async def test_chat_completions_invalid_body(client):
    response = await client.post(
        "/v1/chat/completions",
        json={"model": "test"},  # missing messages
    )
    assert response.status_code == 422  # validation error


@pytest.mark.asyncio
async def test_stream_endpoint(client):
    payload = {
        "model": "claude-sonnet-4-6",
        "messages": [{"role": "user", "content": "hi"}],
        "stream": True,
    }
    response = await client.post("/v1/chat/completions", json=payload)
    # May fail if no API key, but should return proper error
    assert response.status_code in (200, 401, 502)
```

- [ ] **Step 2: Run integration test**

Run: `cd ~/codes/command-code-adapter && poetry run pytest tests/test_integration.py -v`
Expected: Tests pass or return expected status codes

- [ ] **Step 3: Commit**

```bash
git -C ~/codes/command-code-adapter add tests/test_integration.py
git -C ~/codes/command-code-adapter commit -m "test: add integration tests for FastAPI app"
```

---

### Task 10: Final Verification and Documentation

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write README.md**

```markdown
# Command Code Adapter

OpenAI Chat Completions 兼容适配器，用于将 Command Code API 暴露为 OpenAI 格式。

## 快速开始

```bash
# 安装依赖
poetry install

# 配置 API Key
export CC_API_KEY=user_your_key_here

# 启动服务
poetry run python -m cc_adapter
```

## 配置

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `CC_API_KEY` | — | Command Code API Key（必填） |
| `CC_BASE_URL` | `https://api.commandcode.ai` | CC API 地址 |
| `CC_ADAPTER_HOST` | `0.0.0.0` | 监听地址 |
| `CC_ADAPTER_PORT` | `8080` | 监听端口 |
| `CC_ADAPTER_LOG_LEVEL` | `INFO` | 日志级别 |

## 使用

```bash
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-6",
    "messages": [{"role": "user", "content": "Hello"}],
    "stream": true
  }'
```

支持任意 OpenAI SDK：

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8080/v1",
    api_key="not-needed",  # 实际使用 CC_API_KEY
)
```

## 项目结构

```
cc_adapter/
├── main.py          # FastAPI 应用
├── config.py        # 配置
├── models/          # Pydantic 数据模型
├── translator/      # 请求/响应格式转换
├── client.py        # CC API HTTP 客户端
└── errors.py        # 错误处理
```

## 限制

详见 `docs/superpowers/specs/2026-05-06-command-code-adapter-design.md`
```

- [ ] **Step 2: Run full test suite**

Run: `cd ~/codes/command-code-adapter && poetry run pytest -v`
Expected: All tests pass

- [ ] **Step 3: Final commit**

```bash
git -C ~/codes/command-code-adapter add README.md
git -C ~/codes/command-code-adapter commit -m "docs: add README with usage instructions"
```

---

## Spec Coverage Check

| Spec Section | Task |
|-------------|------|
| 项目结构 | Task 1 — pyproject.toml, directory layout |
| 请求转换 (OpenAI→CC) | Task 5 — RequestTranslator |
| 响应转换 (CC→OpenAI) | Task 6 — ResponseTranslator (stream + non-stream) |
| HTTP 服务层 | Task 8 — FastAPI app |
| 配置与认证 | Task 1 (config.py) + Task 7 (client.py) |
| 错误处理 | Task 4 (errors.py) |
| 测试策略 | Task 2-9 |
| S技术支持参数 | Task 5 — _warn_unsupported |
| finish_reason 映射 | Task 6 — FINISH_REASON_MAP |
| SSE 流处理 | Task 6 — translate_stream |
| 非流式模式 | Task 6 — collect_and_translate_nonstream |
| 模型列表端点 | 未实现（不在核心范围，可后续添加） |
