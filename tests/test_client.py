import asyncio

import httpx
import pytest

from council import client
from council.errors import MemberCallError


def _transport(status, body=None):
    def handler(request):
        return httpx.Response(status, json=body or {})

    return httpx.MockTransport(handler)


def test_complete_returns_answer_on_200():
    body = {"choices": [{"message": {"content": "hello"}}]}
    out = asyncio.run(
        client.complete("http://x/v1", "k", "council/a", "hi", transport=_transport(200, body))
    )
    assert out == "hello"


@pytest.mark.parametrize("status,frag", [(401, "401"), (429, "429"), (500, "HTTP 500")])
def test_complete_maps_errors(status, frag):
    with pytest.raises(MemberCallError) as ei:
        asyncio.run(
            client.complete("http://x/v1", "k", "council/a", "hi", transport=_transport(status))
        )
    assert frag in ei.value.detail
