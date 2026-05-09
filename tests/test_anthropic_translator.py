import logging

import pytest

from cc_adapter.anthropic.models import AnthropicMessage, AnthropicRequest
from cc_adapter.anthropic.request import AnthropicTranslator


@pytest.fixture
def translator():
    return AnthropicTranslator()


def test_basic_text_message(translator):
    req = AnthropicRequest(
        model="claude-sonnet-4-6",
        messages=[AnthropicMessage(role="user", content="hello")],
    )
    body, headers = translator.translate(req)
    assert body["params"]["model"] == "claude-sonnet-4-6"
    assert body["params"]["messages"][0]["content"] == [{"type": "text", "text": "hello"}]
    assert "Authorization" not in headers


def test_system_prompt_string(translator):
    req = AnthropicRequest(
        model="claude-sonnet-4-6",
        messages=[AnthropicMessage(role="user", content="hi")],
        system="You are helpful.",
    )
    body, _ = translator.translate(req)
    assert body["params"]["system"] == "You are helpful."


def test_system_prompt_list(translator):
    req = AnthropicRequest(
        model="claude-sonnet-4-6",
        messages=[AnthropicMessage(role="user", content="hi")],
        system=[{"type": "text", "text": "You are helpful."}],
    )
    body, _ = translator.translate(req)
    assert body["params"]["system"] == "You are helpful."


def test_tool_definition(translator):
    req = AnthropicRequest(
        model="claude-sonnet-4-6",
        messages=[AnthropicMessage(role="user", content="read a file")],
        tools=[
            {
                "name": "read",
                "description": "Read a file",
                "input_schema": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            }
        ],
    )
    body, _ = translator.translate(req)
    assert len(body["params"]["tools"]) == 1
    assert body["params"]["tools"][0]["name"] == "read"
    assert body["params"]["tools"][0]["input_schema"]["properties"]["path"]["type"] == "string"


def test_tool_choice_auto(translator):
    req = AnthropicRequest(
        model="claude-sonnet-4-6",
        messages=[AnthropicMessage(role="user", content="hi")],
        tool_choice={"type": "auto"},
    )
    body, _ = translator.translate(req)
    assert body["params"]["tool_choice"] == {"type": "auto"}


def test_tool_choice_tool(translator):
    req = AnthropicRequest(
        model="claude-sonnet-4-6",
        messages=[AnthropicMessage(role="user", content="hi")],
        tool_choice={"type": "tool", "name": "read"},
    )
    body, _ = translator.translate(req)
    assert body["params"]["tool_choice"] == {"type": "tool", "name": "read"}


def test_thinking_maps_to_reasoning_effort_low(translator):
    req = AnthropicRequest(
        model="claude-sonnet-4-6",
        messages=[AnthropicMessage(role="user", content="hello")],
        thinking={"type": "enabled", "budget_tokens": 2000},
    )
    body, _ = translator.translate(req)
    assert body["params"]["reasoning_effort"] == "low"


def test_thinking_maps_to_reasoning_effort_high(translator):
    req = AnthropicRequest(
        model="claude-sonnet-4-6",
        messages=[AnthropicMessage(role="user", content="hello")],
        thinking={"type": "enabled", "budget_tokens": 12000},
    )
    body, _ = translator.translate(req)
    assert body["params"]["reasoning_effort"] == "high"


def test_thinking_maps_to_reasoning_effort_xhigh(translator):
    req = AnthropicRequest(
        model="claude-sonnet-4-6",
        messages=[AnthropicMessage(role="user", content="hello")],
        thinking={"type": "enabled", "budget_tokens": 20000},
    )
    body, _ = translator.translate(req)
    assert body["params"]["reasoning_effort"] == "xhigh"


def test_no_thinking_omits_reasoning_effort(translator):
    req = AnthropicRequest(
        model="claude-sonnet-4-6",
        messages=[AnthropicMessage(role="user", content="hello")],
    )
    body, _ = translator.translate(req)
    assert "reasoning_effort" not in body["params"]


def test_tool_use_content_block(translator):
    req = AnthropicRequest(
        model="claude-sonnet-4-6",
        messages=[
            AnthropicMessage(role="user", content="read file"),
            AnthropicMessage(
                role="assistant",
                content=[
                    {
                        "type": "tool_use",
                        "id": "call_1",
                        "name": "read",
                        "input": {"filePath": "/tmp/test"},
                    }
                ],
            ),
        ],
    )
    body, _ = translator.translate(req)
    msg = body["params"]["messages"][1]
    assert msg["content"] == [
        {
            "type": "tool-call",
            "toolCallId": "call_1",
            "toolName": "read",
            "input": {"path": "/tmp/test"},
        }
    ]


def test_tool_result_content_block(translator):
    req = AnthropicRequest(
        model="claude-sonnet-4-6",
        messages=[
            AnthropicMessage(
                role="user",
                content=[
                    {
                        "type": "tool_result",
                        "tool_use_id": "call_1",
                        "content": "file contents",
                    }
                ],
            ),
        ],
    )
    body, _ = translator.translate(req)
    assert body["params"]["messages"][0]["content"] == [
        {
            "type": "tool-result",
            "toolCallId": "call_1",
            "output": {"type": "text", "value": "file contents"},
        }
    ]


def test_unsupported_params_logged_as_warning(translator, caplog):
    caplog.set_level(logging.WARNING)
    req = AnthropicRequest(
        model="claude-sonnet-4-6",
        messages=[AnthropicMessage(role="user", content="hi")],
        top_p=0.9,
        top_k=5,
        stop_sequences=["\n"],
    )
    translator.translate(req)
    assert any("top_p" in r.message for r in caplog.records)
    assert any("top_k" in r.message for r in caplog.records)
    assert any("stop_sequences" in r.message for r in caplog.records)


def test_image_content_block_skipped(translator, caplog):
    caplog.set_level(logging.WARNING)
    req = AnthropicRequest(
        model="claude-sonnet-4-6",
        messages=[
            AnthropicMessage(
                role="user",
                content=[
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": "abc",
                        },
                    },
                    {"type": "text", "text": "what is this?"},
                ],
            ),
        ],
    )
    body, _ = translator.translate(req)
    assert "Image" in caplog.text
    assert body["params"]["messages"][0]["content"] == [
        {"type": "text", "text": "what is this?"}
    ]
