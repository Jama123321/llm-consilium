# Phase 2b — Rate-limit robustness: usage telemetry, rotation, backoff

**Date:** 2026-07-14
**Status:** Design approved — pending written-spec review, then `writing-plans`.
**Builds on:** Phase 1 engine (`council/`) on `main`. Independent of Phase 2a (systemd/MCP registration).
**Phase map:** Phase 2 = deployment hardening (see Phase 1 spec §14); 2b is its second sub-project.

## 1. Goal & scope

Stop the council burning daily quotas blindly and wasting calls on exhausted providers,
and give visibility into consumption. Adds: a persistent **usage store** (requests +
tokens per member per day), **hard rotation** (skip members at their daily cap),
**bounded backoff** for transient errors (timeout / 5xx, NOT 429 — failover from 1c
already handles 429), and an **observability surface** (a CLI view and a `stats` MCP
tool like Claude Code's usage view).

**In scope:** `council/usage.py` store + eligibility + summary; `rpd`/`tpd` caps in
config; `client.py` recorder + backoff; orchestrator usage-aware selection; a
`scripts/usage.py` CLI; a `stats` MCP tool.
**Out of scope (later):** soft near-cap penalties (only hard skip at cap); backoff for
429; cost/$ tracking; multi-day history/analytics.

## 2. Decisions locked this session

- **Store = SQLite** at `~/.config/consilium/usage.db` (WAL; one connection per op, safe
  across the many short-lived MCP-server processes).
- **Track both requests and tokens** per (alias, day) — providers cap heterogeneously
  (Groq by requests, Cloudflare/Cerebras by tokens).
- **Backoff** applies to timeout/5xx only (2 retries: 0.5s, 1s); 429/401/other-4xx raise
  immediately (fail over).
- **`stats` MCP tool included in 2b** (thin adapter over the store; shares `summary()`
  with the CLI).
- **Telemetry never crashes the council:** a store error degrades to "no rotation".

## 3. Components (each one responsibility)

| Path | Responsibility |
|---|---|
| `council/usage.py` | SQLite `UsageStore` (record/counts) + pure `available()` (rotation filter) + pure `summary()` (view rows) |
| `proxy/config.yaml` (mod) | add optional `model_info.rpd` / `model_info.tpd` per alias |
| `council/registry.py` (mod) | read `rpd`/`tpd` into `Member` |
| `council/types.py` (mod) | `Member` gains `rpd: int | None`, `tpd: int | None` |
| `council/client.py` (mod) | `recorder` callback (records tokens on success) + bounded backoff on timeout/5xx |
| `council/orchestrator.py` (mod) | build the store + recording caller; usage-aware `available` before rank/council; `usage_summary()` |
| `scripts/usage.py` | CLI: print today's per-member requests/tokens vs caps |
| `consilium_mcp/server.py` (mod) | `stats()` MCP tool → `_get_orch().usage_summary()` |

## 4. Data types & interfaces

`Member` gains `rpd: int | None` and `tpd: int | None` (daily request / token budgets;
`None` = uncapped).

```python
# council/usage.py
DEFAULT_DB_PATH = Path.home() / ".config" / "consilium" / "usage.db"

def today() -> str  # UTC "YYYY-MM-DD"

class UsageStore:
    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH) -> None  # create table, PRAGMA wal
    def record(self, alias: str, tokens: int, *, day: str | None = None) -> None
        # UPSERT: requests += 1, tokens += tokens for (alias, day). Swallows DB errors (logged).
    def counts(self, day: str | None = None) -> dict[str, tuple[int, int]]
        # alias -> (requests, tokens) for the day; returns {} on any DB error.

def available(members: list[Member], counts: dict[str, tuple[int, int]]) -> list[Member]
    # drop m where (m.rpd and requests >= m.rpd) or (m.tpd and tokens >= m.tpd)

def summary(members: list[Member], counts: dict[str, tuple[int, int]]) -> list[dict]
    # per member: {alias, tier, requests, tokens, rpd, tpd, exhausted: bool}
```

- `client.complete(..., recorder: Callable[[str, int], None] | None = None,
  max_retries: int = 2, ...)`: on 200, extract `usage.total_tokens` (default 0),
  call `recorder(alias, tokens)` if given, return content. On timeout/5xx: retry up to
  `max_retries` with backoff `(0.5, 1.0)`s, then raise `MemberCallError`. On
  429/401/other-4xx: raise immediately (no retry).
- `client.make_caller(base_url, api_key, *, recorder=None, max_retries=2, ...)`.
- `orchestrator.build(...)`: `store = UsageStore()`; `caller = make_caller(...,
  recorder=store.record)`; `Orchestrator(..., store=store)`.
- `Orchestrator.usage_summary() -> list[dict]` = `usage.summary(self._members,
  self._store.counts())`.

## 5. Config caps (starter values — "verify in console")

Add to each alias's `model_info` where a cap is known (approximate; the audit warns
they drift). A member with neither `rpd` nor `tpd` is never rotated out.

| alias | rpd | tpd | basis |
|---|---|---|---|
| council/cerebras-glm-4.7 | — | 1000000 | Cerebras ~1M tokens/day |
| council/cerebras-gpt-oss-120b | — | 1000000 | shared Cerebras budget |
| council/groq-llama-70b | 1000 | — | Groq ~1k req/day/model |
| council/groq-gpt-oss-120b | 1000 | — | Groq ~1k req/day/model |
| council/cloudflare-llama-70b | — | 10000 | Cloudflare ~10k neurons/day |

(Note: the two Cerebras aliases share one account token budget; tracking is per-alias —
a known approximation, acceptable for a soft guardrail.)

## 6. Behavior

- **Recording:** every successful member call records `(alias, total_tokens)`; a 429/error
  does not record (it did not consume a completion). Requests counter += 1 per success.
- **Rotation:** `ask`/`council` compute `available = usage.available(gate(members), counts)`
  after the privacy gate. If `available` is empty (everyone at cap), fall back to the full
  gated list (better to try — failover handles the resulting 429s). Privacy gate is always
  first; rotation second.
- **Backoff:** transient timeout/5xx → up to 2 retries with 0.5s, 1s; 429 → immediate
  fail-over (no wait).
- **View:** `scripts/usage.py` prints the `summary()` rows; the `stats` MCP tool returns
  the same rows as structured data.

## 7. Error handling

- Telemetry is best-effort: `record()` and `counts()` swallow SQLite errors (log at debug)
  — a broken/locked store yields empty counts → `available` returns all members → no
  rotation, council still works. Telemetry must never crash a call.
- Backoff is bounded (2 retries) so a flaky provider cannot stall a round beyond the
  fan-out timeout.
- No secret is ever written to the usage DB or logged (only aliases + counts).

## 8. Testing (CI-safe, no network)

- `usage`: `record`/`counts` round-trip on a `tmp_path` DB; `available` drops an
  over-`rpd` and an over-`tpd` member and keeps uncapped ones; `summary` shape +
  `exhausted` flag; a corrupt/unwritable path degrades to `{}`/all-available (no raise).
- `registry`: `rpd`/`tpd` parsed (and `None` when absent).
- `client`: `recorder` called with the response's `total_tokens` on success; backoff
  retries a 5xx then succeeds (MockTransport call counter) but does NOT retry a 429;
  timeout retried then raises.
- `orchestrator`: `available` removes an exhausted member from `ask` routing and from the
  `council` trio; empty-available falls back to the full gated list; `usage_summary()`
  returns rows.
- `consilium_mcp`: `stats` tool delegates to `usage_summary` (fake orchestrator).
- Live smoke: after a few `ask`/`council` calls, `scripts/usage.py` shows non-zero
  requests/tokens per member.

## 9. Acceptance criteria

- A member at/over its `rpd` or `tpd` for today is skipped by `ask` and `council`; if all
  are exhausted, calls still proceed against the full gated set.
- Backoff retries timeout/5xx (bounded) and never retries 429.
- `scripts/usage.py` and the `stats` MCP tool both report today's per-member
  requests/tokens vs caps.
- A store failure never crashes a call (degrades to no rotation).
- `ruff` clean + `pytest` green with no keys; no secret in the DB or any tracked file.

## 10. Open notes (non-blocking)

- Cap values are approximate; tune from real usage (visible via `stats`).
- Per-alias token tracking approximates the shared Cerebras account budget — a soft
  guardrail, not exact accounting.
- A `stats` view of multi-day history / cost is deferred.
