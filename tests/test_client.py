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


def test_complete_maps_timeout():
    def handler(request):
        raise httpx.TimeoutException("slow")

    with pytest.raises(MemberCallError) as ei:
        asyncio.run(
            client.complete(
                "http://x/v1", "k", "council/a", "hi", transport=httpx.MockTransport(handler)
            )
        )
    assert ei.value.detail == "timeout"


def test_complete_maps_transport_error():
    def handler(request):
        raise httpx.ConnectError("boom")

    with pytest.raises(MemberCallError) as ei:
        asyncio.run(
            client.complete(
                "http://x/v1", "k", "council/a", "hi", transport=httpx.MockTransport(handler)
            )
        )
    assert ei.value.detail.startswith("request error")


def test_complete_malformed_200_body_raises_member_call_error():
    with pytest.raises(MemberCallError) as ei:
        asyncio.run(
            client.complete(
                "http://x/v1", "k", "council/a", "hi", transport=_transport(200, {"unexpected": 1})
            )
        )
    assert "malformed" in ei.value.detail


def test_make_caller_binds_base_and_key():
    import functools

    caller = client.make_caller("http://x/v1", "k")
    assert isinstance(caller, functools.partial)
    assert caller.args == ("http://x/v1", "k")
