from __future__ import annotations

import functools

import httpx

from council.errors import MemberCallError
from council.types import AsyncCaller


async def complete(
    base_url: str,
    api_key: str,
    alias: str,
    prompt: str,
    *,
    max_tokens: int = 512,
    timeout: float = 30.0,
    transport: httpx.AsyncBaseTransport | None = None,
) -> str:
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {
        "model": alias,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
    }
    try:
        async with httpx.AsyncClient(
            base_url=base_url, headers=headers, timeout=timeout, transport=transport
        ) as http:
            resp = await http.post("/chat/completions", json=payload)
    except httpx.TimeoutException as exc:
        raise MemberCallError(alias, "timeout") from exc
    except httpx.HTTPError as exc:
        raise MemberCallError(alias, f"request error: {exc.__class__.__name__}") from exc
    if resp.status_code != 200:
        detail = {401: "401 auth failed", 429: "429 rate-limited"}.get(
            resp.status_code, f"HTTP {resp.status_code}"
        )
        raise MemberCallError(alias, detail)
    return resp.json()["choices"][0]["message"]["content"]


def make_caller(
    base_url: str, api_key: str, *, max_tokens: int = 512, timeout: float = 30.0
) -> AsyncCaller:
    return functools.partial(
        complete, base_url, api_key, max_tokens=max_tokens, timeout=timeout
    )
