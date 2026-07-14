from __future__ import annotations

import asyncio
import functools
from collections.abc import Callable

import httpx

from council.errors import MemberCallError
from council.types import AsyncCaller

_BACKOFF_DELAYS = (0.5, 1.0)


def _delay(attempt: int) -> float:
    return _BACKOFF_DELAYS[min(attempt, len(_BACKOFF_DELAYS) - 1)]


async def complete(
    base_url: str,
    api_key: str,
    alias: str,
    prompt: str,
    *,
    max_tokens: int = 2048,
    timeout: float = 30.0,
    transport: httpx.AsyncBaseTransport | None = None,
    recorder: Callable[[str, int], None] | None = None,
    max_retries: int = 2,
) -> str:
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {
        "model": alias,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
    }
    attempt = 0
    while True:
        try:
            async with httpx.AsyncClient(
                base_url=base_url, headers=headers, timeout=timeout, transport=transport
            ) as http:
                resp = await http.post("/chat/completions", json=payload)
        except httpx.TimeoutException as exc:
            if attempt < max_retries:
                await asyncio.sleep(_delay(attempt))
                attempt += 1
                continue
            raise MemberCallError(alias, "timeout") from exc
        except httpx.HTTPError as exc:
            raise MemberCallError(alias, f"request error: {exc.__class__.__name__}") from exc

        if resp.status_code == 200:
            return _extract(alias, resp.json(), recorder)
        if resp.status_code >= 500:
            if attempt < max_retries:
                await asyncio.sleep(_delay(attempt))
                attempt += 1
                continue
            raise MemberCallError(alias, f"HTTP {resp.status_code}")
        detail = {401: "401 auth failed", 429: "429 rate-limited"}.get(
            resp.status_code, f"HTTP {resp.status_code}"
        )
        raise MemberCallError(alias, detail)


def _extract(alias: str, data: object, recorder: Callable[[str, int], None] | None) -> str:
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise MemberCallError(alias, "malformed response body") from exc
    if not isinstance(content, str) or not content.strip():
        raise MemberCallError(alias, "empty response content (finish_reason=length?)")
    if recorder is not None:
        tokens = 0
        usage = data.get("usage") if isinstance(data, dict) else None
        if isinstance(usage, dict):
            tokens = int(usage.get("total_tokens") or 0)
        recorder(alias, tokens)
    return content


def make_caller(
    base_url: str,
    api_key: str,
    *,
    recorder: Callable[[str, int], None] | None = None,
    max_retries: int = 2,
    max_tokens: int = 2048,
    timeout: float = 30.0,
) -> AsyncCaller:
    return functools.partial(
        complete,
        base_url,
        api_key,
        recorder=recorder,
        max_retries=max_retries,
        max_tokens=max_tokens,
        timeout=timeout,
    )
