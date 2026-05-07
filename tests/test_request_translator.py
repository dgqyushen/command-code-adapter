import pytest
from cc_adapter.models.openai import ChatCompletionRequest, ChatMessage, ToolDefinition, FunctionDefinition
from cc_adapter.errors import map_upstream_error, AuthenticationError, RateLimitError
from cc_adapter.translator.request import RequestTranslator


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


def test_map_401_to_authentication_error():
    err = map_upstream_error(401, "Unauthorized")
    assert isinstance(err, AuthenticationError)
    assert err.status_code == 401
    assert err.to_openai_error()["error"]["type"] == "authentication_error"


def test_map_429_to_rate_limit_error():
    err = map_upstream_error(429, "Too Many Requests")
    assert isinstance(err, RateLimitError)
    assert err.to_openai_error()["error"]["type"] == "rate_limit_error"


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
    assert body["params"]["messages"][0]["content"] == [{"type": "text", "text": "hello"}]
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


def test_tool_role_converted_to_user(translator):
    req = ChatCompletionRequest(
        model="claude-sonnet-4-6",
        messages=[
            ChatMessage(role="user", content="read file"),
            ChatMessage(
                role="assistant",
                content=None,
                tool_calls=[
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": '{"path":"/tmp/test"}'},
                    }
                ],
            ),
            ChatMessage(role="tool", content="file contents here", tool_call_id="call_1"),
        ],
    )
    body, _ = translator.translate(req)
    msgs = body["params"]["messages"]
    assert len(msgs) == 3
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"
    assert msgs[2]["role"] == "user"
    assert msgs[2]["content"] == [{"type": "text", "text": "file contents here"}]
    assert msgs[2]["tool_call_id"] == "call_1"


def test_content_wrapped_in_array(translator):
    req = ChatCompletionRequest(
        model="claude-sonnet-4-6",
        messages=[
            ChatMessage(role="user", content="hello"),
            ChatMessage(role="assistant", content="hi there"),
        ],
    )
    body, _ = translator.translate(req)
    msgs = body["params"]["messages"]
    assert msgs[0]["content"] == [{"type": "text", "text": "hello"}]
    assert msgs[1]["content"] == [{"type": "text", "text": "hi there"}]


def test_none_content_wrapped_as_empty_string(translator):
    req = ChatCompletionRequest(
        model="claude-sonnet-4-6",
        messages=[
            ChatMessage(role="assistant", content=None),
        ],
    )
    body, _ = translator.translate(req)
    assert body["params"]["messages"][0]["content"] == [{"type": "text", "text": ""}]


def test_stream_true_passed_through(translator):
    req = ChatCompletionRequest(
        model="claude-sonnet-4-6",
        messages=[ChatMessage(role="user", content="hi")],
        stream=True,
    )
    body, _ = translator.translate(req)
    assert body["params"]["stream"] is True


def test_normalize_deepseek_model(translator):
    req = ChatCompletionRequest(
        model="deepseek-v4-flash",
        messages=[ChatMessage(role="user", content="hi")],
    )
    body, _ = translator.translate(req)
    assert body["params"]["model"] == "deepseek/deepseek-v4-flash"


def test_normalize_deepseek_v4_pro(translator):
    req = ChatCompletionRequest(
        model="deepseek-v4-pro",
        messages=[ChatMessage(role="user", content="hi")],
    )
    body, _ = translator.translate(req)
    assert body["params"]["model"] == "deepseek/deepseek-v4-pro"


def test_normalize_qualified_model_passthrough(translator):
    req = ChatCompletionRequest(
        model="deepseek/deepseek-v4-flash",
        messages=[ChatMessage(role="user", content="hi")],
    )
    body, _ = translator.translate(req)
    assert body["params"]["model"] == "deepseek/deepseek-v4-flash"


def test_normalize_default_provider_model_unchanged(translator):
    req = ChatCompletionRequest(
        model="claude-sonnet-4-6",
        messages=[ChatMessage(role="user", content="hi")],
    )
    body, _ = translator.translate(req)
    assert body["params"]["model"] == "claude-sonnet-4-6"
