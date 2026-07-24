import asyncio
import functools

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
            client.complete(
                "http://x/v1", "k", "council/a", "hi",
                transport=_transport(status), max_retries=0,
            )
        )
    assert frag in ei.value.detail


def test_complete_maps_timeout():
    def handler(request):
        raise httpx.TimeoutException("slow")

    with pytest.raises(MemberCallError) as ei:
        asyncio.run(
            client.complete(
                "http://x/v1", "k", "council/a", "hi",
                transport=httpx.MockTransport(handler), max_retries=0,
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


def test_complete_null_content_raises_member_call_error():
    body = {"choices": [{"message": {"content": None}}]}
    with pytest.raises(MemberCallError) as ei:
        asyncio.run(
            client.complete("http://x/v1", "k", "council/a", "hi", transport=_transport(200, body))
        )
    assert "content" in ei.value.detail


def test_complete_empty_content_raises_member_call_error():
    body = {"choices": [{"message": {"content": "   "}}]}
    with pytest.raises(MemberCallError) as ei:
        asyncio.run(
            client.complete("http://x/v1", "k", "council/a", "hi", transport=_transport(200, body))
        )
    assert "content" in ei.value.detail


def test_make_caller_binds_base_and_key():
    caller = client.make_caller("http://x/v1", "k")
    assert isinstance(caller, functools.partial)
    assert caller.args == ("http://x/v1", "k")


def test_backoff_retries_5xx_then_succeeds():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, json={})
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    out = asyncio.run(
        client.complete(
            "http://x/v1", "k", "council/a", "hi",
            transport=httpx.MockTransport(handler), max_retries=2,
        )
    )
    assert out == "ok" and calls["n"] == 2


def test_backoff_retries_429_then_succeeds(monkeypatch):
    monkeypatch.setattr(client, "_delay", lambda attempt: 0.0)
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={})
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    out = asyncio.run(
        client.complete(
            "http://x/v1", "k", "council/a", "hi",
            transport=httpx.MockTransport(handler), max_retries=2,
        )
    )
    assert out == "ok" and calls["n"] == 2


def test_429_exhausted_raises_after_retries(monkeypatch):
    monkeypatch.setattr(client, "_delay", lambda attempt: 0.0)
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(429, json={})

    with pytest.raises(MemberCallError) as ei:
        asyncio.run(
            client.complete(
                "http://x/v1", "k", "council/a", "hi",
                transport=httpx.MockTransport(handler), max_retries=2,
            )
        )
    assert calls["n"] == 3 and "429" in ei.value.detail


def test_429_honors_retry_after_header_capped(monkeypatch):
    slept = []

    async def fake_sleep(secs):
        slept.append(secs)

    monkeypatch.setattr(client.asyncio, "sleep", fake_sleep)
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "120"}, json={})
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    out = asyncio.run(
        client.complete(
            "http://x/v1", "k", "council/a", "hi",
            transport=httpx.MockTransport(handler), max_retries=2,
        )
    )
    assert out == "ok" and slept == [30.0]  # 120 capped to 30


def test_empty_200_records_request_with_zero_tokens():
    seen = []
    body = {"choices": [{"message": {"content": "   "}}]}  # served 200, empty content, no usage

    with pytest.raises(MemberCallError):
        asyncio.run(
            client.complete(
                "http://x/v1", "k", "council/a", "hi",
                transport=_transport(200, body),
                recorder=lambda a, t: seen.append((a, t)),
            )
        )
    assert seen == [("council/a", 0)]  # request counted despite unusable content


def test_recorder_receives_total_tokens():
    seen = []

    def handler(request):
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}}], "usage": {"total_tokens": 42}},
        )

    asyncio.run(
        client.complete(
            "http://x/v1", "k", "council/a", "hi",
            transport=httpx.MockTransport(handler), recorder=lambda a, t: seen.append((a, t)),
        )
    )
    assert seen == [("council/a", 42)]
