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
