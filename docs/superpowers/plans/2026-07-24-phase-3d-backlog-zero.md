# Phase 3d — "backlog zero" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close all nine deferred-backlog items (2 fixes, 4 test gaps, 3 feature items) so the repo can go public with an empty, honest known-issues list and a green gate.

**Architecture:** Small, additive changes across `council/` and `consilium_mcp/`. The two "feature" items (multi-day history, cost tracking) need **no `usage.db` schema migration** — `day` is already in the primary key and cost is derived from `tokens × rate` at read time. Every public MCP signature stays backward compatible.

**Tech Stack:** Python 3.10, asyncio/httpx (MockTransport in tests), sqlite3, pytest, ruff.

## Global Constraints

- Secrets — only `~/.config/consilium/.env`, never in code/git/memory. No item logs content to any Tier-B provider; the `runlog.py` redaction gate is unchanged.
- All changes additive: MCP `ask`/`council`/`stats` call signatures stay backward compatible (`stats` gains optional `days=1`).
- No `usage.db` schema migration.
- `ruff check .` clean + `pytest` green is the hard gate. Commits English imperative, **no `Co-Authored-By`**. Branch `phase-3d` (already created off `main`).
- New `Member` field must be appended **last** so existing positional constructions (e.g. `Member("r","A",{...},5,"r",rpd=2)`) keep working.

## File map
- `council/client.py` — 429 retry+backoff, `Retry-After` cap, record request on every served 200 (Task 1).
- `council/aggregate.py` + `council/orchestrator.py` — plumb `timeout` into peer-rank/debate (Task 2).
- `consilium/env_file.py` — drop redundant chmod (Task 3).
- `council/types.py` + `council/registry.py` + `council/usage.py` — cost tracking (Task 4).
- `council/usage.py` + `council/orchestrator.py` — multi-day history (Task 5).
- `consilium_mcp/server.py` — `stats(days=1)` (Task 6).
- Tests only: `tests/test_usage.py`, `tests/test_runlog.py` (Task 7).
- `docs/superpowers/STATUS.md` — backlog → empty (Task 8).

---

### Task 1: client.py — 429 backoff + accurate 200 accounting (#7, #6)

**Files:**
- Modify: `council/client.py`
- Test: `tests/test_client.py`

**Interfaces:**
- Consumes: `MemberCallError(alias, detail)`, `_delay(attempt)`, `_BACKOFF_DELAYS`.
- Produces: `_retry_after(resp) -> float | None` (capped at `_MAX_RETRY_AFTER = 30.0`); `_token_count(data) -> int`; unchanged `complete(...)` signature; 429 now retries up to `max_retries`; a served 200 records the request before body validation.

- [ ] **Step 1: Replace the outdated 429 test with retry tests.** In `tests/test_client.py`, DELETE `test_no_retry_on_429` (lines ~117-131) and add:

```python
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
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `.venv/bin/pytest tests/test_client.py -q`
Expected: the four new tests FAIL (429 currently raises immediately / empty-200 records nothing); `test_no_retry_on_429` is gone.

- [ ] **Step 3: Implement the client changes.** In `council/client.py`, add `_MAX_RETRY_AFTER` and `_retry_after` near `_delay`:

```python
_BACKOFF_DELAYS = (0.5, 1.0)
_MAX_RETRY_AFTER = 30.0


def _delay(attempt: int) -> float:
    return _BACKOFF_DELAYS[min(attempt, len(_BACKOFF_DELAYS) - 1)]


def _retry_after(resp: httpx.Response) -> float | None:
    raw = resp.headers.get("Retry-After")
    if raw is None:
        return None
    try:
        secs = float(int(raw))
    except (TypeError, ValueError):
        return None  # HTTP-date form or garbage -> fall back to exponential backoff
    return min(max(secs, 0.0), _MAX_RETRY_AFTER)
```

Replace the status-dispatch block (currently `if resp.status_code == 200 ... raise MemberCallError(alias, detail)`) with:

```python
        if resp.status_code == 200:
            return _extract(alias, resp.json(), recorder)
        if resp.status_code == 429:
            if attempt < max_retries:
                ra = _retry_after(resp)
                await asyncio.sleep(ra if ra is not None else _delay(attempt))
                attempt += 1
                continue
            raise MemberCallError(alias, "429 rate-limited")
        if resp.status_code >= 500:
            if attempt < max_retries:
                await asyncio.sleep(_delay(attempt))
                attempt += 1
                continue
            raise MemberCallError(alias, f"HTTP {resp.status_code}")
        detail = {401: "401 auth failed"}.get(resp.status_code, f"HTTP {resp.status_code}")
        raise MemberCallError(alias, detail)
```

Replace `_extract` with a version that records the served request first, then validates:

```python
def _extract(alias: str, data: object, recorder: Callable[[str, int], None] | None) -> str:
    # A 200 means the provider served (and metered) the request, so record it before
    # validating the body — otherwise an empty/malformed 200 would silently under-count
    # usage against the daily cap.
    if recorder is not None:
        recorder(alias, _token_count(data))
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise MemberCallError(alias, "malformed response body") from exc
    if not isinstance(content, str) or not content.strip():
        raise MemberCallError(alias, "empty response content (finish_reason=length?)")
    return content


def _token_count(data: object) -> int:
    usage = data.get("usage") if isinstance(data, dict) else None
    if isinstance(usage, dict):
        return int(usage.get("total_tokens") or 0)
    return 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_client.py -q`
Expected: PASS (incl. `test_recorder_receives_total_tokens` still records 42, `test_complete_maps_errors[429]` with `max_retries=0` still raises).

- [ ] **Step 5: Commit**

```bash
git add council/client.py tests/test_client.py
git commit -m "fix(3d): retry 429 with capped Retry-After backoff; count served 200s"
```

---

### Task 2: aggregate + orchestrator — plumb timeout (#1)

**Files:**
- Modify: `council/aggregate.py`, `council/orchestrator.py`
- Test: `tests/test_aggregate.py`, `tests/test_orchestrator.py`

**Interfaces:**
- Produces: `aggregate(prompt, answers, *, caller, judge_aliases, rng=None, mode=None, timeout: float = 30.0)` forwards `timeout` to `_peer_rank`/`_debate`; `Orchestrator(__init__ ..., call_timeout: float = 30.0)` forwards it as `aggregate(..., timeout=self._call_timeout)`.
- Consumes: `AggregateResult` (from `council.types`), existing `_peer_rank`/`_debate` `timeout` kwargs.

- [ ] **Step 1: Write failing forwarding tests.** In `tests/test_aggregate.py`, add `AggregateResult` to the imports (`from council.types import AggregateResult, MemberAnswer`) and add:

```python
def test_aggregate_forwards_timeout_to_debate(monkeypatch):
    captured = {}

    async def fake_debate(prompt, ok_members, *, caller, judge_aliases, rng,
                          max_rounds=2, threshold=0.7, timeout=30.0):
        captured["timeout"] = timeout
        return AggregateResult("x", "debate", "", None, "high")

    monkeypatch.setattr(aggregate, "_debate", fake_debate)
    ans = _answers(("m1", True, "one long enough answer"), ("m2", True, "two long enough answer"))
    asyncio.run(
        aggregate.aggregate(
            "q", ans, caller=_judge, judge_aliases=["chair"], mode="debate", timeout=7.5
        )
    )
    assert captured["timeout"] == 7.5


def test_aggregate_forwards_timeout_to_peer_rank(monkeypatch):
    captured = {}

    async def fake_peer_rank(prompt, ok_members, *, caller, judge_aliases, rng, timeout=30.0):
        captured["timeout"] = timeout
        return AggregateResult("x", "peer-rank", "", None, "high")

    monkeypatch.setattr(aggregate, "_peer_rank", fake_peer_rank)
    ans = _answers(("m1", True, "one long enough answer"), ("m2", True, "two long enough answer"))
    asyncio.run(
        aggregate.aggregate(
            "q", ans, caller=_judge, judge_aliases=["chair"], mode="peer-rank", timeout=3.0
        )
    )
    assert captured["timeout"] == 3.0
```

In `tests/test_orchestrator.py`, add (uses existing `AggregateResult` import path — add `from council.types import Member` already present, add `AggregateResult`):

```python
def test_council_passes_call_timeout_to_aggregate(monkeypatch):
    from council import aggregate as agg_mod
    from council.types import AggregateResult
    captured = {}

    async def fake_aggregate(prompt, answers, *, caller, judge_aliases, rng=None,
                             mode=None, timeout=30.0):
        captured["timeout"] = timeout
        return AggregateResult("x", "judge", "", "chair", "high")

    monkeypatch.setattr(agg_mod, "aggregate", fake_aggregate)
    o = Orchestrator(ALL, Recorder(), call_timeout=12.0)
    asyncio.run(o.council("explain the tradeoffs in depth please"))
    assert captured["timeout"] == 12.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_aggregate.py::test_aggregate_forwards_timeout_to_debate tests/test_orchestrator.py::test_council_passes_call_timeout_to_aggregate -q`
Expected: FAIL — `aggregate()`/`Orchestrator` don't accept `timeout`/`call_timeout` yet.

- [ ] **Step 3: Implement the plumbing.** In `council/aggregate.py`, change the `aggregate` signature and the two dispatch branches:

```python
async def aggregate(
    prompt: str,
    answers: list[MemberAnswer],
    *,
    caller: AsyncCaller,
    judge_aliases: list[str],
    rng: random.Random | None = None,
    mode: str | None = None,
    timeout: float = 30.0,
) -> AggregateResult:
```

```python
    if mode == "peer-rank":
        return await _peer_rank(
            prompt, ok_members, caller=caller, judge_aliases=judge_aliases,
            rng=rng, timeout=timeout,
        )
    if mode == "debate":
        return await _debate(
            prompt, ok_members, caller=caller, judge_aliases=judge_aliases,
            rng=rng, timeout=timeout,
        )
```

In `council/orchestrator.py`, add `call_timeout` to `__init__` and store it:

```python
    def __init__(
        self,
        members: list[Member],
        caller: AsyncCaller,
        *,
        classifier_alias: str = CLASSIFIER_ALIAS,
        chair_alias: str = CHAIR_ALIAS,
        store: usage.UsageStore | None = None,
        runlog: runlog_module.RunLog | None = None,
        call_timeout: float = 30.0,
    ) -> None:
        self._members = members
        self._caller = caller
        self._classifier_alias = classifier_alias
        self._chair_alias = chair_alias
        self._store = store
        self._runlog = runlog
        self._call_timeout = call_timeout
```

In `council/orchestrator.py` `council()`, pass the timeout:

```python
        result = await agg.aggregate(
            prompt, answers, caller=self._caller,
            judge_aliases=self._judge_order(chosen), mode=mode, timeout=self._call_timeout,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_aggregate.py tests/test_orchestrator.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add council/aggregate.py council/orchestrator.py tests/test_aggregate.py tests/test_orchestrator.py
git commit -m "fix(3d): plumb call timeout into peer-rank/debate aggregation"
```

---

### Task 3: env_file.py — drop redundant chmod (#2)

**Files:**
- Modify: `consilium/env_file.py`
- Test: `tests/test_env_file.py` (existing perms tests are the regression guard)

**Interfaces:**
- Produces: `write(path, values)` unchanged behaviour; the atomic write no longer calls `os.chmod` (mkstemp already yields 0o600 on POSIX), closing the theoretical fd-leak window.

- [ ] **Step 1: Confirm the regression tests exist.** `tests/test_env_file.py::test_write_sets_posix_permissions` and `::test_write_tightens_perms_on_preexisting_loose_file` both assert the written file is `0o600`. No new test needed — they must keep passing after the change.

- [ ] **Step 2: Run them (baseline green)**

Run: `.venv/bin/pytest tests/test_env_file.py -q`
Expected: PASS (baseline before the edit).

- [ ] **Step 3: Remove the redundant chmod.** In `consilium/env_file.py`, replace the write tail (the `fd, tmp = tempfile.mkstemp(...)` block and its comment) with:

```python
    content = "\n".join(lines).rstrip() + "\n"
    # Secure atomic write: mkstemp creates the temp file mode 0o600 on POSIX (owner
    # read/write only) — no world-readable window, so no follow-up chmod is needed.
    # os.replace atomically swaps it in, replacing any pre-existing symlink at the
    # destination rather than following it. Keeping nothing between mkstemp and fdopen
    # also removes the theoretical fd-leak on an interim failure.
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".env-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(tmp, p)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
```

(The `import os` stays — `os.fdopen`/`os.replace`/`os.name` elsewhere still use it; `os` is still imported.)

- [ ] **Step 4: Run tests to verify still green**

Run: `.venv/bin/pytest tests/test_env_file.py -q`
Expected: PASS — mkstemp still yields 0o600, so both perms tests hold; the symlink and roundtrip tests are unaffected.

- [ ] **Step 5: Commit**

```bash
git add consilium/env_file.py
git commit -m "refactor(3d): drop redundant chmod after mkstemp (closes fd-leak window)"
```

---

### Task 4: Cost tracking (#9)

**Files:**
- Modify: `council/types.py`, `council/registry.py`, `council/usage.py`
- Test: `tests/test_types.py`, `tests/test_registry.py`, `tests/test_usage.py`

**Interfaces:**
- Produces: `Member(..., cost_per_1k: float = 0.0)` (appended last); `registry.load_members` reads `model_info.cost_per_1k` (default 0.0); `usage.summary(...)` rows gain `"cost_usd" = round(tokens / 1000 * cost_per_1k, 6)`.
- Consumes: existing `Member`, `registry.load_members`, `usage.summary`.

- [ ] **Step 1: Write failing tests.**

In `tests/test_types.py` add:

```python
def test_member_cost_per_1k_defaults_zero():
    m = Member(alias="a", privacy_tier="A", scores={"general": 3}, rpm=5)
    assert m.cost_per_1k == 0.0
```

In `tests/test_registry.py` add:

```python
def test_cost_per_1k_defaults_zero_for_free_members():
    assert _members()["council/cerebras-glm-4.7"].cost_per_1k == 0.0


def test_cost_per_1k_parsed_from_model_info(tmp_path):
    cfg = tmp_path / "priced.yaml"
    cfg.write_text(
        "model_list:\n"
        "  - model_name: council/priced\n"
        "    litellm_params: {model: groq/x, rpm: 7}\n"
        "    model_info: {privacy_tier: A, scores: {general: 3}, cost_per_1k: 1.5}\n"
    )
    m = {x.alias: x for x in registry.load_members(cfg)}["council/priced"]
    assert m.cost_per_1k == 1.5
```

In `tests/test_usage.py` add a priced member fixture and tests (place the fixture near the other module-level members):

```python
PRICED = Member("p", "A", {"general": 3}, 5, "p", cost_per_1k=2.0)


def test_summary_computes_cost_usd_from_tokens_and_rate():
    counts = {"p": (3, 1500)}  # 1500 tokens * $2.0 / 1k = $3.0
    rows = {row["alias"]: row for row in usage.summary([PRICED], counts)}
    assert rows["p"]["cost_usd"] == 3.0


def test_summary_cost_usd_zero_for_free_member():
    counts = {"u": (1, 1000)}
    rows = {row["alias"]: row for row in usage.summary([UNCAPPED], counts)}
    assert rows["u"]["cost_usd"] == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_types.py tests/test_registry.py tests/test_usage.py -q`
Expected: FAIL — `Member` has no `cost_per_1k`; `summary` has no `cost_usd`.

- [ ] **Step 3: Implement.** In `council/types.py`, append the field to `Member` (after `tpd`):

```python
    tpd: int | None = None
    cost_per_1k: float = 0.0
```

In `council/registry.py`, add to the `Member(...)` construction in `load_members`:

```python
                rpd=int(rpd) if rpd is not None else None,
                tpd=int(tpd) if tpd is not None else None,
                cost_per_1k=float(info.get("cost_per_1k", 0.0)),
```

In `council/usage.py` `summary`, add the `cost_usd` key to each row dict:

```python
        rows.append(
            {
                "alias": m.alias,
                "tier": m.privacy_tier,
                "requests": req,
                "tokens": tok,
                "rpd": m.rpd,
                "tpd": m.tpd,
                "exhausted": _exhausted(m, counts),
                "cost_usd": round(tok / 1000 * m.cost_per_1k, 6),
            }
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_types.py tests/test_registry.py tests/test_usage.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add council/types.py council/registry.py council/usage.py tests/test_types.py tests/test_registry.py tests/test_usage.py
git commit -m "feat(3d): track per-member cost_usd (0 for all free members)"
```

---

### Task 5: Multi-day usage history (#8)

**Files:**
- Modify: `council/usage.py`, `council/orchestrator.py`
- Test: `tests/test_usage.py`, `tests/test_orchestrator.py`

**Interfaces:**
- Produces: `UsageStore.history(days: int = 7, *, end_day: str | None = None) -> list[dict]` — rows `{"day","alias","requests","tokens"}`, newest day first, best-effort `[]` on error. `Orchestrator.usage_history(days: int = 7) -> list[dict]` delegates (`[]` without a store).
- Consumes: existing `UsageStore._connect`, `today()`.

- [ ] **Step 1: Write failing tests.** In `tests/test_usage.py` add:

```python
def test_history_returns_days_newest_first(tmp_path):
    store = usage.UsageStore(tmp_path / "u.db")
    store.record("r", 10, day="2026-07-20")
    store.record("r", 20, day="2026-07-22")
    store.record("s", 5, day="2026-07-22")
    rows = store.history(days=7, end_day="2026-07-22")
    assert rows[0]["day"] == "2026-07-22"  # newest first
    by_key = {(row["day"], row["alias"]): row for row in rows}
    assert by_key[("2026-07-22", "r")]["tokens"] == 20
    assert by_key[("2026-07-20", "r")]["requests"] == 1


def test_history_excludes_days_before_window(tmp_path):
    store = usage.UsageStore(tmp_path / "u.db")
    store.record("r", 10, day="2026-07-10")
    store.record("r", 20, day="2026-07-22")
    rows = store.history(days=3, end_day="2026-07-22")  # window 2026-07-20..22
    assert all(row["day"] >= "2026-07-20" for row in rows)
    assert not any(row["day"] == "2026-07-10" for row in rows)
```

In `tests/test_orchestrator.py` add:

```python
def test_usage_history_delegates_to_store():
    class HStore:
        def history(self, days=7):
            return [{"day": "2026-07-22", "alias": "council/x", "requests": 1, "tokens": 5}]

    o = Orchestrator(ALL, Recorder(), store=HStore())
    assert o.usage_history(3)[0]["day"] == "2026-07-22"


def test_usage_history_empty_without_store():
    assert Orchestrator(ALL, Recorder()).usage_history() == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_usage.py::test_history_returns_days_newest_first tests/test_orchestrator.py::test_usage_history_empty_without_store -q`
Expected: FAIL — `history`/`usage_history` don't exist.

- [ ] **Step 3: Implement.** In `council/usage.py`, extend the datetime import and add the method to `UsageStore`:

```python
from datetime import datetime, timedelta, timezone
```

```python
    def history(self, days: int = 7, *, end_day: str | None = None) -> list[dict]:
        end = end_day or today()
        start = (
            datetime.strptime(end, "%Y-%m-%d") - timedelta(days=max(days - 1, 0))
        ).strftime("%Y-%m-%d")
        try:
            with closing(self._connect()) as conn:
                rows = conn.execute(
                    "SELECT day, alias, requests, tokens FROM usage "
                    "WHERE day >= ? AND day <= ? ORDER BY day DESC, alias",
                    (start, end),
                ).fetchall()
        except (sqlite3.Error, OSError):
            return []
        return [
            {"day": d, "alias": a, "requests": req, "tokens": tok}
            for d, a, req, tok in rows
        ]
```

In `council/orchestrator.py`, add next to `usage_summary`:

```python
    def usage_history(self, days: int = 7) -> list[dict]:
        return self._store.history(days) if self._store is not None else []
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_usage.py tests/test_orchestrator.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add council/usage.py council/orchestrator.py tests/test_usage.py tests/test_orchestrator.py
git commit -m "feat(3d): add multi-day usage history query"
```

---

### Task 6: MCP stats(days) — surface history + cost (#8, #9)

**Files:**
- Modify: `consilium_mcp/server.py`
- Test: `tests/test_mcp_server.py`

**Interfaces:**
- Consumes: `Orchestrator.usage_summary()` (now with `cost_usd` per row) and `Orchestrator.usage_history(days)` (Task 5).
- Produces: `stats(days: int = 1) -> dict` = `{"today": [...], "total_cost_usd": float}`, plus `"history": [...]` when `days > 1`. Zero-arg call still valid (signature backward compatible); the return shape becomes a richer dict.

- [ ] **Step 1: Update the stats tests for the dict shape.** In `tests/test_mcp_server.py`, REPLACE `test_stats_delegates_to_usage_summary` with:

```python
def test_stats_returns_today_and_total_cost(monkeypatch):
    class FakeOrch:
        def usage_summary(self):
            return [{"alias": "council/x", "requests": 2, "tokens": 10,
                     "exhausted": False, "cost_usd": 0.0}]

    monkeypatch.setattr(server, "_orch", FakeOrch())
    import asyncio

    out = asyncio.run(server.stats())
    assert out["today"][0]["alias"] == "council/x" and out["today"][0]["requests"] == 2
    assert out["total_cost_usd"] == 0.0
    assert "history" not in out  # days=1 -> no history block


def test_stats_days_includes_history(monkeypatch):
    class FakeOrch:
        def usage_summary(self):
            return [{"alias": "council/x", "requests": 1, "tokens": 5, "cost_usd": 0.0}]

        def usage_history(self, days):
            return [{"day": "2026-07-23", "alias": "council/x", "requests": 1, "tokens": 5}]

    monkeypatch.setattr(server, "_orch", FakeOrch())
    import asyncio

    out = asyncio.run(server.stats(days=7))
    assert out["history"][0]["day"] == "2026-07-23"
    assert out["total_cost_usd"] == 0.0
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/pytest tests/test_mcp_server.py -q`
Expected: FAIL — `stats` returns a list and takes no `days`.

- [ ] **Step 3: Implement.** In `consilium_mcp/server.py`, replace the `stats` tool:

```python
@mcp.tool()
async def stats(days: int = 1) -> dict:
    """Consilium usage vs daily caps.

    days: 1 (default) returns today's per-member summary plus a total cost line;
        days > 1 additionally returns a per-day history (newest first).
    Returns: {today: [per-member rows incl. cost_usd], total_cost_usd, history?}.
    """
    o = _get_orch()
    today_rows = o.usage_summary()
    out = {
        "today": today_rows,
        "total_cost_usd": round(sum(r.get("cost_usd", 0.0) for r in today_rows), 6),
    }
    if days > 1:
        out["history"] = o.usage_history(days)
    return out
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest tests/test_mcp_server.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add consilium_mcp/server.py tests/test_mcp_server.py
git commit -m "feat(3d): stats(days) surfaces multi-day history and total cost"
```

---

### Task 7: Close the test-coverage gaps (#3, #4, #5)

**Files:**
- Test only: `tests/test_usage.py`, `tests/test_runlog.py` (no production code change)

**Interfaces:**
- Consumes: `UsageStore` graceful degradation on `sqlite3.Error`/`OSError`; `runlog._redact` skipping non-str answers.

- [ ] **Step 1: Add the corrupt-DB and hermetic unwritable-path tests.** In `tests/test_usage.py`, ADD `test_store_survives_corrupt_db` and REPLACE `test_store_survives_unwritable_path` with the hermetic version:

```python
def test_store_survives_corrupt_db(tmp_path):
    db = tmp_path / "corrupt.db"
    db.write_bytes(b"this is not a sqlite database at all")
    store = usage.UsageStore(db)   # init must not raise on a corrupt-but-writable file
    store.record("r", 5)           # must not raise
    assert store.counts() == {}    # degrades to empty


def test_store_survives_unwritable_path(tmp_path):
    # Hermetic under any uid (incl. root): the db path's parent is a regular file, so
    # mkdir raises NotADirectoryError (an OSError) that a root uid cannot bypass.
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    store = usage.UsageStore(blocker / "nested" / "u.db")
    store.record("r", 5)          # must not raise
    assert store.counts() == {}   # degrades to empty
```

- [ ] **Step 2: Add the Tier-B None-answer redaction test.** In `tests/test_runlog.py`, ADD:

```python
def test_redact_handles_none_member_answer(tmp_path):
    # A Tier-B member that abstained has answer=None; redaction must leave it None,
    # add no answer_len, and not raise.
    path = tmp_path / "runs.jsonl"
    log = RunLog(path, enabled=True)
    log.record(
        {"tool": "council", "per_member": [{"alias": "council/b", "ok": False, "answer": None}]},
        redact=True,
    )
    member = _read_lines(path)[0]["per_member"][0]
    assert member["answer"] is None
    assert "answer_len" not in member
    assert member["alias"] == "council/b"
```

- [ ] **Step 3: Run the new/changed tests to verify they pass** (these document already-correct behaviour, so they pass immediately)

Run: `.venv/bin/pytest tests/test_usage.py tests/test_runlog.py -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/test_usage.py tests/test_runlog.py
git commit -m "test(3d): cover corrupt DB, hermetic unwritable path, None-answer redaction"
```

---

### Task 8: STATUS.md — backlog → empty

**Files:**
- Modify: `docs/superpowers/STATUS.md`

- [ ] **Step 1: Rewrite the "Deferred backlog" section.** In `docs/superpowers/STATUS.md`, replace the `## Deferred backlog (non-blocking)` list body with:

```markdown
## Deferred backlog (non-blocking)
- **Empty** — all prior items closed by Phase 3d (backlog-zero hardening, 2026-07-24):
  429 retry/backoff + Retry-After cap, served-200 usage accounting, aggregation timeout
  plumbing, mkstemp chmod cleanup, cost tracking, multi-day history, and the corrupt-DB /
  hermetic-unwritable-path / None-answer-redaction test gaps. See the 3d spec+plan under
  `docs/superpowers/{specs,plans}/2026-07-24-phase-3d-*`.
```

Also update the "Next steps" `3b MERGED ... 3c ... merge` line context if needed to note 3d, and leave the go-public step as user-gated.

- [ ] **Step 2: Run the full gate**

Run: `.venv/bin/ruff check . && .venv/bin/pytest -q`
Expected: ruff clean, all tests PASS (baseline 188 + the ~15 new/changed 3d tests).

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/STATUS.md
git commit -m "docs(3d): mark deferred backlog empty after backlog-zero wave"
```

---

## Self-review

**Spec coverage:** #1 timeout → Task 2; #2 chmod → Task 3; #3 corrupt-DB → Task 7; #4 unwritable-path hermetic → Task 7; #5 None-answer redaction → Task 7; #6 empty-200 → Task 1; #7 429 backoff → Task 1; #8 multi-day → Tasks 5+6; #9 cost → Tasks 4+6. STATUS backlog→empty → Task 8. All nine covered.

**Placeholder scan:** No TBD/TODO; every code step shows full code and exact `.venv/bin/pytest` commands with expected pass/fail.

**Type consistency:** `cost_per_1k: float` defined in `Member` (Task 4) and read in `registry` (Task 4), consumed in `usage.summary` (Task 4) and surfaced via `stats` (Task 6). `history(days, *, end_day)` defined in `UsageStore` (Task 5), delegated by `Orchestrator.usage_history(days)` (Task 5), consumed by `stats` (Task 6). `aggregate(..., timeout=)` (Task 2) matches `_peer_rank`/`_debate` existing `timeout` kwargs and `Orchestrator.call_timeout` (Task 2). `_retry_after` / `_token_count` (Task 1) are self-contained. Test edits that would otherwise break are explicitly replaced: `test_no_retry_on_429` (Task 1), `test_stats_delegates_to_usage_summary` (Task 6), `test_store_survives_unwritable_path` (Task 7).

**Ordering:** Tasks 4 and 5 precede Task 6 (which consumes `cost_usd` and `usage_history`). Tasks 1/2/3/7 are independent. Task 8 runs the full gate last.
