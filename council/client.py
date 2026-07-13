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
    max_tokens: int = 2048,
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
    try:
        content = resp.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise MemberCallError(alias, "malformed response body") from exc
    if not isinstance(content, str) or not content.strip():
        raise MemberCallError(alias, "empty response content (finish_reason=length?)")
    return content


def make_caller(
    base_url: str, api_key: str, *, max_tokens: int = 2048, timeout: float = 30.0
) -> AsyncCaller:
    return functools.partial(
        complete, base_url, api_key, max_tokens=max_tokens, timeout=timeout
    )
