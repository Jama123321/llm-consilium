# Phase 2b — Rate-limit robustness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-member usage telemetry (SQLite), hard rotation past daily caps, bounded backoff for transient errors, and a usage view (CLI + `stats` MCP tool).

**Architecture:** A `council/usage.py` SQLite store records requests+tokens per member per day; the client records tokens on success and retries timeout/5xx with backoff; the orchestrator drops daily-exhausted members after the privacy gate; a CLI and a `stats` MCP tool share `usage.summary()`.

**Tech Stack:** Python 3.10 stdlib `sqlite3`, `asyncio`/`httpx`, pytest/ruff.

## Global Constraints

- Store = SQLite at `~/.config/consilium/usage.db` (WAL; connection per op; best-effort — a store error degrades to "no rotation", never crashes a call).
- Track BOTH requests and tokens per `(alias, day)` (UTC date). Record only on a successful completion.
- Backoff: timeout / 5xx only, up to 2 retries with delays `(0.5, 1.0)`s; 429/401/other-4xx raise immediately.
- `Member` gains `rpd: int | None` and `tpd: int | None` (defaults `None` = uncapped) — added AFTER `rpm`, so existing positional `Member(alias, tier, caps, strength, rpm)` construction still works.
- Rotation runs AFTER the privacy gate; if every gated member is exhausted, fall back to the full gated list. Direct `ask(model=…)` respects the gate, not rotation.
- Secrets never written to the DB or logs (only aliases + counts). Commits: English, imperative, **NO `Co-Authored-By` trailer**. Stay on branch `phase-2b-ratelimit`. Tools as `.venv/bin/<tool>`.

## File Structure

| Path | Responsibility | Task |
|---|---|---|
| `council/types.py` (mod) | `Member` gains `rpd`/`tpd` | 1 |
| `proxy/config.yaml` (mod) | per-alias `rpd`/`tpd` caps | 1 |
| `council/registry.py` (mod) | read `rpd`/`tpd` | 1 |
| `council/usage.py` | `UsageStore` + `available()` + `summary()` + `today()` | 2 |
| `council/client.py` (mod) | `recorder` callback + backoff | 3 |
| `council/orchestrator.py` (mod) | build store + recording caller; usage-aware selection; `usage_summary()` | 4 |
| `scripts/usage.py` | CLI usage view | 5 |
| `consilium_mcp/server.py` (mod) | `stats` MCP tool | 6 |

---

### Task 1: `Member` daily caps + config + registry

**Files:**
- Modify: `council/types.py`, `proxy/config.yaml`, `council/registry.py`
- Test: `tests/test_registry.py`

**Interfaces:**
- Produces: `Member(..., rpd: int | None = None, tpd: int | None = None)`; registry reads `model_info.rpd`/`model_info.tpd`.

- [ ] **Step 1: Add the failing test**

Append to `tests/test_registry.py`:
```python
def test_daily_caps_parsed():
    m = _members()
    assert m["council/groq-llama-70b"].rpd == 1000
    assert m["council/groq-llama-70b"].tpd is None
    assert m["council/cloudflare-llama-70b"].tpd == 10000
    assert m["council/cloudflare-llama-70b"].rpd is None
    assert m["council/cerebras-glm-4.7"].tpd == 1000000
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_registry.py::test_daily_caps_parsed -q`
Expected: FAIL — `Member` has no `rpd`/`tpd`; config has no caps.

- [ ] **Step 3: Add `rpd`/`tpd` to `Member` in `council/types.py`**

Replace the `Member` dataclass with:
```python
@dataclass(frozen=True)
class Member:
    alias: str
    privacy_tier: str
    capabilities: tuple[str, ...]
    strength: int
    rpm: int
    rpd: int | None = None
    tpd: int | None = None
```

- [ ] **Step 4: Add caps to `proxy/config.yaml`**

Add the indicated line(s) inside each alias's existing `model_info` block (keep `privacy_tier`, `strength`, `capabilities`):
- `council/cerebras-glm-4.7` → add `tpd: 1000000`
- `council/cerebras-gpt-oss-120b` → add `tpd: 1000000`
- `council/groq-llama-70b` → add `rpd: 1000`
- `council/groq-gpt-oss-120b` → add `rpd: 1000`
- `council/cloudflare-llama-70b` → add `tpd: 10000`

- [ ] **Step 5: Read caps in `council/registry.py`**

In `load_members`, replace the `Member(...)` construction with one that reads the caps:
```python
        info = entry.get("model_info") or {}
        params = entry.get("litellm_params") or {}
        rpd = info.get("rpd")
        tpd = info.get("tpd")
        members.append(
            Member(
                alias=entry["model_name"],
                privacy_tier=info.get("privacy_tier", "B"),
                capabilities=tuple(info.get("capabilities", ["general"])),
                strength=int(info.get("strength", 1)),
                rpm=int(params.get("rpm", 10)),
                rpd=int(rpd) if rpd is not None else None,
                tpd=int(tpd) if tpd is not None else None,
            )
        )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_registry.py tests/test_config.py tests/test_types.py -q`
Expected: PASS (new caps test + all existing registry/config/types tests still green — the new fields default `None` so positional `Member(...)` construction elsewhere is unaffected).

- [ ] **Step 7: Lint & commit**

```bash
.venv/bin/ruff check .
git add council/types.py proxy/config.yaml council/registry.py tests/test_registry.py
git commit -m "feat: add per-member daily request/token caps (rpd/tpd)"
```

---

### Task 2: `council/usage.py` — SQLite store, rotation filter, summary

**Files:**
- Create: `council/usage.py`, `tests/test_usage.py`

**Interfaces:**
- Consumes: `Member` (with `rpd`/`tpd`).
- Produces: `usage.today() -> str`; `UsageStore(db_path=DEFAULT_DB_PATH)` with `.record(alias, tokens, *, day=None)` and `.counts(day=None) -> dict[str, tuple[int,int]]`; `usage.available(members, counts) -> list[Member]`; `usage.summary(members, counts) -> list[dict]`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_usage.py`:
```python
from council import usage
from council.types import Member

CAPPED_REQ = Member("r", "A", ("general",), 3, 5, rpd=2, tpd=None)
CAPPED_TOK = Member("t", "A", ("general",), 3, 5, rpd=None, tpd=100)
UNCAPPED = Member("u", "A", ("general",), 3, 5)


def test_record_and_counts_roundtrip(tmp_path):
    store = usage.UsageStore(tmp_path / "u.db")
    store.record("r", 40, day="2026-07-14")
    store.record("r", 10, day="2026-07-14")
    assert store.counts("2026-07-14") == {"r": (2, 50)}


def test_available_drops_over_rpd_and_tpd():
    counts = {"r": (2, 0), "t": (1, 100)}  # r at rpd=2, t at tpd=100
    got = usage.available([CAPPED_REQ, CAPPED_TOK, UNCAPPED], counts)
    assert [m.alias for m in got] == ["u"]


def test_available_keeps_under_cap():
    counts = {"r": (1, 0), "t": (1, 50)}
    got = usage.available([CAPPED_REQ, CAPPED_TOK, UNCAPPED], counts)
    assert {m.alias for m in got} == {"r", "t", "u"}


def test_summary_shape_and_exhausted_flag():
    counts = {"r": (2, 0)}
    rows = {row["alias"]: row for row in usage.summary([CAPPED_REQ, UNCAPPED], counts)}
    assert rows["r"]["requests"] == 2 and rows["r"]["rpd"] == 2 and rows["r"]["exhausted"] is True
    assert rows["u"]["exhausted"] is False and rows["u"]["tokens"] == 0


def test_store_survives_unwritable_path():
    store = usage.UsageStore("/nonexistent-dir-xyz/u.db")
    store.record("r", 5)          # must not raise
    assert store.counts() == {}   # degrades to empty
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_usage.py -q`
Expected: FAIL — `council.usage` does not exist.

- [ ] **Step 3: Create `council/usage.py`**

```python
from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from council.types import Member

DEFAULT_DB_PATH = Path.home() / ".config" / "consilium" / "usage.db"

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS usage ("
    "alias TEXT NOT NULL, day TEXT NOT NULL, "
    "requests INTEGER NOT NULL DEFAULT 0, tokens INTEGER NOT NULL DEFAULT 0, "
    "PRIMARY KEY (alias, day))"
)


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class UsageStore:
    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH) -> None:
        self._path = str(db_path)
        try:
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
            with closing(self._connect()) as conn, conn:
                conn.execute(_SCHEMA)
        except sqlite3.Error:
            pass  # best-effort; a broken store degrades to no telemetry

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, timeout=5)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def record(self, alias: str, tokens: int, *, day: str | None = None) -> None:
        d = day or today()
        try:
            with closing(self._connect()) as conn, conn:
                conn.execute(
                    "INSERT INTO usage (alias, day, requests, tokens) VALUES (?, ?, 1, ?) "
                    "ON CONFLICT(alias, day) DO UPDATE SET "
                    "requests = requests + 1, tokens = tokens + excluded.tokens",
                    (alias, d, int(tokens)),
                )
        except sqlite3.Error:
            pass  # never crash a call on telemetry

    def counts(self, day: str | None = None) -> dict[str, tuple[int, int]]:
        d = day or today()
        try:
            with closing(self._connect()) as conn:
                rows = conn.execute(
                    "SELECT alias, requests, tokens FROM usage WHERE day = ?", (d,)
                ).fetchall()
        except sqlite3.Error:
            return {}
        return {alias: (req, tok) for alias, req, tok in rows}


def _exhausted(m: Member, counts: dict[str, tuple[int, int]]) -> bool:
    req, tok = counts.get(m.alias, (0, 0))
    return (m.rpd is not None and req >= m.rpd) or (m.tpd is not None and tok >= m.tpd)


def available(members: list[Member], counts: dict[str, tuple[int, int]]) -> list[Member]:
    return [m for m in members if not _exhausted(m, counts)]


def summary(members: list[Member], counts: dict[str, tuple[int, int]]) -> list[dict]:
    rows = []
    for m in members:
        req, tok = counts.get(m.alias, (0, 0))
        rows.append(
            {
                "alias": m.alias,
                "tier": m.privacy_tier,
                "requests": req,
                "tokens": tok,
                "rpd": m.rpd,
                "tpd": m.tpd,
                "exhausted": _exhausted(m, counts),
            }
        )
    return rows
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_usage.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Lint & commit**

```bash
.venv/bin/ruff check .
git add council/usage.py tests/test_usage.py
git commit -m "feat: add SQLite usage store with rotation filter and summary"
```

---

### Task 3: `council/client.py` — token recorder + bounded backoff

**Files:**
- Modify: `council/client.py`
- Test: `tests/test_client.py`

**Interfaces:**
- Produces: `client.complete(..., recorder: Callable[[str,int],None] | None = None, max_retries: int = 2, ...)` — records `total_tokens` on success; retries timeout/5xx (delays `(0.5, 1.0)`), immediate raise on 429/401/4xx. `client.make_caller(..., recorder=None, max_retries=2, ...)`.

- [ ] **Step 1: Update existing tests + add new ones in `tests/test_client.py`**

The existing `test_complete_maps_errors` parametrizes 401/429/500 — 500 would now be retried (slow). Change ONLY its `500` case to pass `max_retries=0`, and its 401/429 cases keep the default (they never retry). Simplest: give that test a `max_retries=0` argument in the `complete(...)` call so it tests the pure mapping without backoff delay. Then the timeout test `test_complete_maps_timeout` also passes `max_retries=0`. Append these new tests:
```python
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


def test_no_retry_on_429():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(429, json={})

    with pytest.raises(client.MemberCallError):
        asyncio.run(
            client.complete(
                "http://x/v1", "k", "council/a", "hi",
                transport=httpx.MockTransport(handler), max_retries=2,
            )
        )
    assert calls["n"] == 1


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
```
Note: `client.MemberCallError` may not be exported from `client`; if the test file already imports `MemberCallError` from `council.errors`, use that name instead (keep the file's existing import).

- [ ] **Step 2: Run to verify the new tests fail**

Run: `.venv/bin/pytest tests/test_client.py -q`
Expected: FAIL — no backoff/recorder yet (5xx not retried; recorder unused).

- [ ] **Step 3: Rewrite `council/client.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_client.py -q`
Expected: PASS (existing mapping tests with `max_retries=0` + the 3 new tests).

- [ ] **Step 5: Lint & commit**

```bash
.venv/bin/ruff check .
git add council/client.py tests/test_client.py
git commit -m "feat: record response tokens and back off on transient errors"
```

---

### Task 4: `council/orchestrator.py` — usage-aware selection + summary

**Files:**
- Modify: `council/orchestrator.py`
- Test: `tests/test_orchestrator.py`

**Interfaces:**
- Consumes: `usage` (Task 2), `client.make_caller(recorder=…)` (Task 3).
- Produces: `Orchestrator(..., store: usage.UsageStore | None = None)`; `ask`/`council` drop exhausted members after the gate (fallback to gated list when all exhausted); `Orchestrator.usage_summary() -> list[dict]`; `build()` wires a `UsageStore` + recording caller.

- [ ] **Step 1: Add failing tests to `tests/test_orchestrator.py`**

Add near the top-level imports:
```python
from council import usage
```
Append (the module already defines `GLM`, `GROQ`, `CF`, `ALL`, `Recorder`, `_orch`):
```python
class _FakeStore:
    def __init__(self, counts):
        self._counts = counts

    def counts(self, day=None):
        return self._counts


def test_council_skips_exhausted_member():
    # GLM exhausted by tpd; council should fall back to the remaining trio members
    store = _FakeStore({"council/cerebras-glm-4.7": (0, 10**9)})
    members = [
        Member("council/cerebras-glm-4.7", "A", ("reasoning",), 5, 5, tpd=1000000),
        GROQ, CF,
    ]
    o = Orchestrator(members, Recorder(), store=store)
    r = asyncio.run(o.council("explain the tradeoffs in depth please"))
    assert "council/cerebras-glm-4.7" not in {a.alias for a in r.per_member}


def test_council_falls_back_when_all_exhausted():
    store = _FakeStore({m.alias: (0, 10**9) for m in [GLM, GROQ, CF]})
    members = [
        Member(GLM.alias, "A", GLM.capabilities, 5, 5, tpd=1),
        Member(GROQ.alias, "A", GROQ.capabilities, 4, 30, tpd=1),
        Member(CF.alias, "A", CF.capabilities, 3, 10, tpd=1),
    ]
    o = Orchestrator(members, Recorder(), store=store)
    r = asyncio.run(o.council("explain the tradeoffs in depth please"))
    assert len(r.per_member) == 3  # fell back to the full gated trio


def test_usage_summary_returns_rows():
    o = Orchestrator(ALL, Recorder(), store=_FakeStore({"council/cerebras-glm-4.7": (3, 500)}))
    rows = {row["alias"]: row for row in o.usage_summary()}
    assert rows["council/cerebras-glm-4.7"]["requests"] == 3
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/pytest tests/test_orchestrator.py -q`
Expected: FAIL — `Orchestrator` has no `store`/`usage_summary`; no rotation.

- [ ] **Step 3: Edit `council/orchestrator.py`**

Add the import (with the other `from council import ...` line):
```python
from council import aggregate as agg
from council import client, fanout, privacy, registry, router, usage
```
Add `store` to `__init__` (after `default_member_aliases`):
```python
        default_member_aliases: tuple[str, ...] = DEFAULT_MEMBER_ALIASES,
        store: usage.UsageStore | None = None,
    ) -> None:
        self._members = members
        self._caller = caller
        self._classifier_alias = classifier_alias
        self._chair_alias = chair_alias
        self._default_member_aliases = default_member_aliases
        self._store = store
```
Add a helper and `usage_summary` (e.g. after `_by_alias`):
```python
    def _counts(self) -> dict[str, tuple[int, int]]:
        return self._store.counts() if self._store is not None else {}

    def usage_summary(self) -> list[dict]:
        return usage.summary(self._members, self._counts())
```
In `ask`, after `allowed = privacy.allowed_members(...)`, add:
```python
        pool = usage.available(allowed, self._counts()) or allowed
```
and change the auto/capability loop to iterate `router.rank(pool, capability)` (the direct `model=` path keeps checking `allowed`, unchanged).
In `council`, after `allowed = privacy.allowed_members(...)`, replace the `chosen = ...` line with:
```python
        pool = usage.available(allowed, self._counts()) or allowed
        wanted = members or self._default_member_aliases
        chosen = [m for m in pool if m.alias in wanted] or [
            m for m in allowed if m.alias in wanted
        ]
```
In `build(...)`, wire the store + recording caller:
```python
def build(
    config_path: str = "proxy/config.yaml", *, base_url: str = DEFAULT_BASE_URL, api_key: str
) -> Orchestrator:
    members = registry.load_members(config_path)
    store = usage.UsageStore()
    caller = client.make_caller(base_url, api_key, recorder=store.record)
    return Orchestrator(members, caller, store=store)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_orchestrator.py -q`
Expected: PASS (the 3 new tests + all existing orchestrator tests — existing ones construct `Orchestrator(ALL, caller)` with `store=None`, so `_counts()` is `{}`, `available` returns all, behavior unchanged).

- [ ] **Step 5: Full gate, lint & commit**

```bash
.venv/bin/ruff check . && .venv/bin/pytest -q
git add council/orchestrator.py tests/test_orchestrator.py
git commit -m "feat: skip daily-exhausted members and expose usage summary"
```

---

### Task 5: `scripts/usage.py` — CLI usage view

**Files:**
- Create: `scripts/usage.py`

**Interfaces:**
- Consumes: `registry.load_members`, `usage.UsageStore`, `usage.summary`.

- [ ] **Step 1: Create `scripts/usage.py`**

```python
#!/usr/bin/env python3
"""Print today's per-member Consilium usage vs daily caps."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from council import registry, usage  # noqa: E402

CONFIG = Path(__file__).resolve().parents[1] / "proxy" / "config.yaml"


def main() -> int:
    members = registry.load_members(CONFIG)
    rows = usage.summary(members, usage.UsageStore().counts())
    header = f"{'alias':32} {'tier':4} {'req':>6} {'tokens':>10} {'rpd':>8} {'tpd':>10}  flag"
    print(header)
    print("-" * len(header))
    for r in rows:
        flag = "EXHAUSTED" if r["exhausted"] else ""
        print(
            f"{r['alias']:32} {r['tier']:4} {r['requests']:>6} {r['tokens']:>10} "
            f"{str(r['rpd'] if r['rpd'] is not None else '-'):>8} "
            f"{str(r['tpd'] if r['tpd'] is not None else '-'):>10}  {flag}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Verify it runs (no live proxy needed)**

Run: `.venv/bin/python scripts/usage.py`
Expected: prints a header + one row per alias (today's counts, likely 0 on a fresh DB), exit 0. `.venv/bin/ruff check .` clean.

- [ ] **Step 3: Commit**

```bash
git add scripts/usage.py
git commit -m "feat: add CLI to view per-member daily usage"
```

---

### Task 6: `stats` MCP tool + docs + final gate

**Files:**
- Modify: `consilium_mcp/server.py`, `docs/usage-rule.md`
- Test: `tests/test_mcp_server.py`

**Interfaces:**
- Consumes: `Orchestrator.usage_summary()` (Task 4).
- Produces: MCP tool `stats() -> list[dict]`.

- [ ] **Step 1: Add the failing test**

Append to `tests/test_mcp_server.py`:
```python
def test_stats_delegates_to_usage_summary(monkeypatch):
    class FakeOrch:
        def usage_summary(self):
            return [{"alias": "council/x", "requests": 2, "tokens": 10, "exhausted": False}]

    monkeypatch.setattr(server, "_orch", FakeOrch())
    import asyncio

    rows = asyncio.run(server.stats())
    assert rows[0]["alias"] == "council/x" and rows[0]["requests"] == 2
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_mcp_server.py::test_stats_delegates_to_usage_summary -q`
Expected: FAIL — `server.stats` does not exist.

- [ ] **Step 3: Add the `stats` tool to `consilium_mcp/server.py`**

After the `council` tool, add:
```python
@mcp.tool()
async def stats() -> list[dict]:
    """Today's per-member Consilium usage (requests, tokens) vs daily caps."""
    return _get_orch().usage_summary()
```

- [ ] **Step 4: Update `docs/usage-rule.md`**

In the `## Free-LLM council (consilium MCP)` fenced block, add one bullet after the `council(...)` bullet:
```
- `stats()` — today's per-member usage (requests, tokens) vs daily caps; use to check
  headroom before a heavy `council` call.
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_mcp_server.py -q`
Expected: PASS (existing MCP tests + the new stats test).

- [ ] **Step 6: Full gate, lint & commit**

```bash
.venv/bin/ruff check . && .venv/bin/pytest -q
git add consilium_mcp/server.py tests/test_mcp_server.py docs/usage-rule.md
git commit -m "feat: add stats MCP tool exposing per-member usage"
```

---

## Self-Review

**Spec coverage (against `2026-07-14-phase-2b-ratelimit-telemetry-design.md`):**
- §3 components → `types`+config+`registry` (T1), `usage` (T2), `client` (T3), `orchestrator` (T4), `scripts/usage.py` (T5), `stats` tool (T6). ✓
- §4 interfaces → `Member.rpd/tpd`, `UsageStore.record/counts`, `available`, `summary`, `client.complete(recorder,max_retries)`, `Orchestrator.usage_summary`, `build` wiring — all defined with matching names/signatures. ✓
- §5 config caps → T1 Step 4 (exact values). ✓
- §6 behavior (record on success; rotation after gate; fallback when all exhausted; direct respects gate; backoff timeout/5xx not 429) → T3 + T4, asserted by `test_no_retry_on_429`, `test_backoff_retries_5xx`, `test_council_skips_exhausted_member`, `test_council_falls_back_when_all_exhausted`. ✓
- §7 error handling (store best-effort, no crash) → T2 `UsageStore` try/except + `test_store_survives_unwritable_path`. ✓
- §8 testing → each task's tests; live smoke via `scripts/usage.py`. ✓
- §9 acceptance → T4 gate + T5/T6 views. ✓

**Placeholder scan:** No TBD/TODO; every step shows full content. ✓

**Type consistency:** `Member(rpd,tpd)`, `UsageStore.record/counts`, `available`, `summary`, `_exhausted`, `client.complete(recorder,max_retries)`, `make_caller(recorder,…)`, `Orchestrator(store=…)`, `usage_summary`, `stats` — names match across defining and consuming tasks. Existing `Member(...)` positional construction remains valid (new fields default `None`). `Orchestrator(ALL, caller)` remains valid (`store` defaults `None`). ✓
