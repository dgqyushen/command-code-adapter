import pytest
from cc_adapter.models.openai import ChatCompletionRequest
from cc_adapter.errors import map_upstream_error, AuthenticationError, RateLimitError


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
