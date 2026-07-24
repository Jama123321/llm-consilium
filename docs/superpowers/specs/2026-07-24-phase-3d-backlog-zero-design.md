# Phase 3d — "backlog zero" (hardening before go-public) — design/spec

> Status: approved by user 2026-07-24. Final hardening mini-phase before the repo is
> flipped public. Closes every item in the STATUS.md deferred backlog so the public
> repo ships with an empty, honest "known issues" list and a green gate.

## Business context

This is the last cleanup before the repository becomes public. A public project with a
non-empty "known issues" list reads as unfinished; closing all nine deferred items and
reducing the backlog to zero lets the council ship with a green gate, accurate telemetry,
and an honest "backlog: empty" line. None of the items touch privacy/secrets, and every
change is additive — the public MCP interface (`ask`/`council`/`stats`) stays backward
compatible.

## Goal

Close all nine deferred-backlog items from `docs/superpowers/STATUS.md` in a single
hardening wave: two real fixes, four test-coverage gaps, and three previously-deferred
"feature" items (429 client backoff, multi-day usage history, cost tracking) — the last
three implemented **without a schema migration**. Then mark the backlog empty in STATUS.

## Global Constraints (verbatim)

- Secrets — only `~/.config/consilium/.env`, never in code/git/memory. No item logs content
  to any Tier-B provider; the redaction gate in `runlog.py` is unchanged.
- All changes are **additive**: MCP `ask`/`council`/`stats` signatures stay backward
  compatible (`stats` gains an optional `days=1` that defaults to today's behaviour).
- `ruff` clean + `pytest` green is the hard gate. All SDD subagents on Opus. Commits English
  imperative, **no `Co-Authored-By`**. Branch `phase-3d` off `main`. Never merge to `main`
  without explicit user OK.
- No `usage.db` schema migration: the `day` column is already part of the primary key, and
  cost is derived at read time from `tokens × rate`.

## Backlog → task mapping (all nine items)

| # | Backlog item (STATUS) | Class | Component |
|---|-----------------------|-------|-----------|
| 1 | 2d `_peer_rank`/`_debate` timeout not plumbed | fix | aggregate.py + orchestrator.py |
| 2 | 3a redundant chmod after mkstemp + theoretical fd-leak | fix | env_file.py |
| 3 | 2b corrupt-writable-DB test | test | tests/test_usage.py |
| 4 | 2b unwritable-path test non-hermetic under uid 0 | test | tests/test_usage.py |
| 5 | 2e Tier-B `None`-answer through redaction | test | tests/test_runlog.py |
| 6 | 2b empty-200 records nothing | fix+test | client.py |
| 7 | 2c 429 exponential backoff | feature | client.py |
| 8 | 2c multi-day usage history | feature | usage.py + orchestrator.py + MCP |
| 9 | 2c cost/$ tracking | feature | types.py + registry.py + usage.py + MCP |

## Components

### 1. `council/client.py` — 429 backoff + accurate 200 accounting (#7, #6)

- **429 becomes retryable** (like 5xx): when `attempt < max_retries`, `await asyncio.sleep(
  retry_after if present else _delay(attempt))`, increment, retry; on exhaustion raise
  `MemberCallError(alias, "429 rate-limited")`.
- The `Retry-After` response header (integer seconds) is honoured **but capped at 30 s** so a
  hostile/large value cannot hang the council. Non-integer / absent → fall back to `_delay`.
- **empty-200 accounting:** a 200 means the provider served the request (quota spent), so the
  request is recorded (`recorder(alias, 0)` when the token count is unavailable) **before**
  `_extract` raises on empty/malformed content. This fixes "empty-200 records nothing" — RPD
  accounting no longer undercounts served-but-unusable responses.

### 2. `council/aggregate.py` + `council/orchestrator.py` — plumb timeout (#1)

- `aggregate(prompt, answers, *, caller, judge_aliases, rng=None, mode=None, timeout: float =
  30.0)` forwards `timeout` to `_peer_rank(..., timeout=timeout)` and `_debate(...,
  timeout=timeout)` (both currently hardcode 30.0).
- `Orchestrator.__init__(..., call_timeout: float = 30.0)` stores the value; `council()` calls
  `agg.aggregate(..., timeout=self._call_timeout)`. One configuration point instead of three
  hardcodes. `build()` keeps the 30 s default.

### 3. `consilium/env_file.py` — drop redundant chmod (#2)

- `tempfile.mkstemp` already creates the file `0o600` on POSIX, so the explicit
  `if os.name == "posix": os.chmod(tmp, 0o600)` is removed. Removing it also closes the
  theoretical fd-leak window (no throwing operation remains between `mkstemp` and `os.fdopen`).
  A comment documents that mkstemp guarantees 0o600. The existing 0o600 regression test stays.

### 4. Cost tracking (#9) — vertical slice, no migration

- `council/types.py`: `Member` gains `cost_per_1k: float = 0.0`.
- `council/registry.py`: `load_members` reads `model_info.cost_per_1k` (default `0.0`), same
  pattern as the existing `scores` dossier read.
- `proxy/config.yaml`: all free members keep cost 0 (field simply absent → default 0), so the
  report shows `$0.00` — the honest "it's free" signal.
- `council/usage.py`: `summary()` rows gain `cost_usd = round(tokens / 1000 * m.cost_per_1k,
  6)`. The DB schema is unchanged; cost is computed from stored tokens at read time.

### 5. Multi-day history (#8) — no migration

- `council/usage.py`: `UsageStore.history(days: int = 7, *, end_day: str | None = None) ->
  list[dict]` returns rows `{"day", "alias", "requests", "tokens"}` for the last `days` days
  (`WHERE day >= ? ORDER BY day DESC, alias`), best-effort (`[]` on `sqlite3.Error`/`OSError`).
  `end_day` defaults to `today()`; the start day is `end_day − (days − 1)`.
- `council/orchestrator.py`: `usage_history(days: int = 7) -> list[dict]` delegates to the
  store (`[]` when no store).

### 6. `consilium_mcp/server.py` — `stats(days: int = 1)` (#8, #9)

- `stats(days: int = 1)`: `days == 1` keeps the current behaviour (today's per-member summary)
  and adds a total `cost_usd` line; `days > 1` additionally returns the per-day history from
  `usage_history`. Fully additive — existing zero-arg calls are unchanged.

### 7. Test-coverage gaps (#3, #4, #5) — tests only, no production code change

- **2b corrupt-writable-DB** (`tests/test_usage.py`): write non-SQLite bytes to a writable db
  path, assert `UsageStore(path).counts()` returns `{}` and `record()` does not raise.
- **2b unwritable-path hermetic under uid 0** (`tests/test_usage.py`): set the db path *under a
  regular file* (parent is a file, not a dir) so `parent.mkdir` raises `NotADirectoryError`
  (an `OSError`) even as root; assert `UsageStore` init/`record`/`counts` degrade without
  raising. Replaces / augments any perms-based test that a root uid would bypass.
- **2e Tier-B `None`-answer** (`tests/test_runlog.py`): `_redact({"per_member": [{"alias": "x",
  "answer": None}]})` leaves `answer` as `None`, adds no `answer_len`, and does not raise.

## Out of scope

- `usage.db` schema migration (not needed). Real non-zero tariffs in the config (all members
  are free → 0). Retroactive recomputation of history. New MCP tools (only `stats` gains an
  optional arg).

## Files

- Modify: `council/client.py`, `council/aggregate.py`, `council/orchestrator.py`,
  `council/types.py`, `council/registry.py`, `council/usage.py`, `consilium/env_file.py`,
  `consilium_mcp/server.py`, `proxy/config.yaml` (only if a cost field is documented — else
  untouched).
- Tests: `tests/test_client.py`, `tests/test_aggregate.py`, `tests/test_orchestrator.py`,
  `tests/test_usage.py`, `tests/test_registry.py`, `tests/test_types.py`,
  `tests/test_env_file.py`, `tests/test_mcp_server.py`, `tests/test_runlog.py`.
- Docs: update `docs/superpowers/STATUS.md` — backlog → empty.
