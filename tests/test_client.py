import pytest
from cc_adapter.client import CommandCodeClient
from cc_adapter.errors import AuthenticationError


@pytest.mark.asyncio
async def test_client_requires_api_key():
    client = CommandCodeClient(base_url="https://api.commandcode.ai", api_key="")
    with pytest.raises(AuthenticationError, match="CC_API_KEY is not configured"):
        async for _ in client.generate({"params": {"model": "test", "messages": []}}):
            pass
