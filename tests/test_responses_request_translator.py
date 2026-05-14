from __future__ import annotations

import pytest
from cc_adapter.core.errors import AdapterError
from cc_adapter.providers.openai.responses_request import ResponsesRequestTranslator
from cc_adapter.providers.openai.responses_models import ResponseCreateRequest


@pytest.fixture
def translator():
    return ResponsesRequestTranslator()


@pytest.mark.asyncio
async def test_simple_string_input(translator):
    req = ResponseCreateRequest(model="deepseek-v4-flash", input="Hello")
    body, headers = translator.translate(req)
    params = body["params"]
    assert params["model"] == "deepseek/deepseek-v4-flash"
    assert len(params["messages"]) == 1
    assert params["messages"][0]["role"] == "user"
    assert params["messages"][0]["content"][0]["text"] == "Hello"
    assert params["stream"] is True
    assert params["max_tokens"] == 64000


@pytest.mark.asyncio
async def test_instructions_mapped_to_system(translator):
    req = ResponseCreateRequest(model="deepseek-v4-flash", input="Hi", instructions="Be concise")
    body, headers = translator.translate(req)
    assert body["params"]["system"] == "Be concise"


@pytest.mark.asyncio
async def test_temperature_passthrough(translator):
    req = ResponseCreateRequest(model="deepseek-v4-flash", input="Hi", temperature=0.7)
    body, headers = translator.translate(req)
    assert body["params"]["temperature"] == 0.7


@pytest.mark.asyncio
async def test_max_output_tokens_mapped(translator):
    req = ResponseCreateRequest(model="deepseek-v4-flash", input="Hi", max_output_tokens=100)
    body, headers = translator.translate(req)
    assert body["params"]["max_tokens"] == 100


@pytest.mark.asyncio
async def test_reasoning_effort_mapped(translator):
    req = ResponseCreateRequest(model="deepseek-v4-flash", input="Hi", reasoning={"effort": "high"})
    body, headers = translator.translate(req)
    assert body["params"]["reasoning_effort"] == "high"


@pytest.mark.asyncio
async def test_tools(translator):
    req = ResponseCreateRequest(
        model="deepseek-v4-flash",
        input="Read the file",
        tools=[
            {
                "name": "Read",
                "description": "Read a file",
                "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
            }
        ],
    )
    body, headers = translator.translate(req)
    assert len(body["params"]["tools"]) == 1
    assert body["params"]["tools"][0]["name"] == "Read"


@pytest.mark.asyncio
async def test_tool_choice_auto(translator):
    req = ResponseCreateRequest(
        model="deepseek-v4-flash", input="Hi", tools=[{"name": "Read", "input_schema": {}}], tool_choice="auto"
    )
    body, headers = translator.translate(req)
    assert body["params"]["tool_choice"] == {"type": "auto"}


@pytest.mark.asyncio
async def test_tool_choice_none(translator):
    req = ResponseCreateRequest(model="deepseek-v4-flash", input="Hi", tool_choice="none")
    body, headers = translator.translate(req)
    assert body["params"]["tool_choice"] == {"type": "none"}


@pytest.mark.asyncio
async def test_multi_turn_input_list(translator):
    req = ResponseCreateRequest(
        model="deepseek-v4-flash",
        input=[
            {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Hello"}]},
            {"type": "message", "role": "assistant", "content": [{"type": "input_text", "text": "Hi there"}]},
            {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "How are you?"}]},
        ],
    )
    body, headers = translator.translate(req)
    assert len(body["params"]["messages"]) == 3
    assert body["params"]["messages"][0]["role"] == "user"
    assert body["params"]["messages"][1]["role"] == "assistant"
    assert body["params"]["messages"][2]["role"] == "user"


@pytest.mark.asyncio
async def test_function_call_output_in_input(translator):
    req = ResponseCreateRequest(
        model="deepseek-v4-flash",
        input=[
            {"type": "function_call", "call_id": "call_1", "name": "Read", "arguments": '{"path": "/tmp/test.txt"}'},
            {"type": "function_call_output", "call_id": "call_1", "output": "file content"},
        ],
    )
    body, headers = translator.translate(req)
    assert len(body["params"]["messages"]) == 2
    assert body["params"]["messages"][0]["role"] == "assistant"
    assert body["params"]["messages"][0]["content"][0]["type"] == "tool-call"
    assert body["params"]["messages"][1]["role"] == "tool"
    assert body["params"]["messages"][1]["content"][0]["type"] == "tool-result"


@pytest.mark.asyncio
async def test_unknown_model_passthrough(translator):
    req = ResponseCreateRequest(model="unknown-model-42", input="Hi")
    body, headers = translator.translate(req)
    assert body["params"]["model"] == "unknown-model-42"


@pytest.mark.asyncio
async def test_output_text_content_block_not_stringified(translator):
    req = ResponseCreateRequest(
        model="deepseek-v4-flash",
        input=[
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "Previous answer"}],
            },
            {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Tell me more"}]},
        ],
    )
    body, headers = translator.translate(req)
    msgs = body["params"]["messages"]
    assert len(msgs) == 2
    assert msgs[0]["content"][0]["type"] == "text"
    assert msgs[0]["content"][0]["text"] == "Previous answer"


@pytest.mark.asyncio
async def test_previous_response_id_raises_400(translator):
    req = ResponseCreateRequest(model="deepseek-v4-flash", input="Hi", previous_response_id="resp_prev")
    with pytest.raises(AdapterError) as exc:
        translator.translate(req)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_response_format_raises_400(translator):
    req = ResponseCreateRequest(model="deepseek-v4-flash", input="Hi", response_format={"type": "json_object"})
    with pytest.raises(AdapterError) as exc:
        translator.translate(req)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_built_in_tool_raises_400(translator):
    req = ResponseCreateRequest(
        model="deepseek-v4-flash",
        input="search",
        tools=[{"type": "web_search_preview"}],
    )
    with pytest.raises(AdapterError) as exc:
        translator.translate(req)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_function_tool_passes_validation(translator):
    req = ResponseCreateRequest(
        model="deepseek-v4-flash",
        input="do it",
        tools=[{"name": "my_func", "input_schema": {"type": "object", "properties": {}}}],
    )
    body, headers = translator.translate(req)
    assert len(body["params"]["tools"]) == 1
    assert body["params"]["tools"][0]["name"] == "my_func"
