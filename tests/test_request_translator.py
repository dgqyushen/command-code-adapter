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
