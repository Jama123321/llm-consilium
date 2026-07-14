# Phase 1 — Council Orchestrator + MCP + Usage Protocol

**Date:** 2026-07-13
**Status:** Design approved — pending written-spec review, then `writing-plans`.
**Builds on:** Phase 0 (`docs/superpowers/specs/2026-07-13-phase-0-mvp-proxy-design.md`) — a live LiteLLM proxy on `127.0.0.1:4000` fronting 5 Tier-A aliases.
**Design basis:** `docs/research/free-llm-consilium-audit-2026.md`, `CLAUDE.md`.

## 1. Goal & scope

Turn the Phase-0 compute layer into a tool Claude uses in **every** project: ask one
best-fit model (`ask`) or convene a cross-checking council (`council`), both behind a
**privacy gate**. Expose both as a **user-scope MCP server**, and append a **usage
protocol** to `~/.claude/CLAUDE.md`.

This merges the originally-separate Phase 1 (orchestrator) and Phase 2 (MCP) into one
wave, per the decision to ship MCP immediately. It is **one cohesive subsystem** (the
MCP server is a thin adapter over the orchestrator), so it gets one spec; the
implementation plan splits into two sub-waves that each produce working, testable
software:

- **1a — Engine:** `registry → privacy → router → client → fanout → aggregate →
  orchestrator`, provable via a live smoke script.
- **1b — Surface:** the MCP server exposing `ask`/`council`, plus the usage rule in
  `~/.claude/CLAUDE.md`.
- **1c — Resilience:** rate-limit fallback for `ask` and the judge, so hitting a free
  provider's RPM/quota degrades gracefully instead of erroring (added after the live
  1a smoke repeatedly hit Cerebras's ~5 RPM cap). See §13.

**Out of scope (later phases — now "Phase 2 · Deployment hardening"):** adding Tier-B
providers, systemd always-on service, quota/RPD telemetry + daily member rotation,
exponential backoff, 1-round debate aggregation. See the phase map in §14.

## 2. Decisions locked this session

- **`ask` default = auto:** with no `model`, the router picks the single best member.
- **Routing = router classifies the prompt itself** (a meta-call to the fastest member
  → a capability label), then selects by capability + strength. **Fast-path:** if the
  caller passes `capability`, the classify call is skipped.
- **Aggregation = adaptive:** judge-synthesis by default; majority-vote when answers are
  clearly closed-form (yes/no, pick-an-option).
- **Two MCP tools:** `ask` (single model, auto or direct) and `council` (fan-out).
- **Capability metadata lives in `proxy/config.yaml`** `model_info` (single source of
  truth, already holds `privacy_tier`); the registry parses the YAML directly.
- **Privacy gate** is caller-driven via `sensitivity` (default `sensitive`) and includes
  a defensive secret-pattern refusal.
- **Stack:** Python 3.10, `asyncio`/`httpx`, MCP Python SDK, `pytest`/`ruff`.

## 3. Components (each one responsibility)

```
council/
  __init__.py
  registry.py      # load Members from proxy/config.yaml
  privacy.py       # sensitivity → allowed tiers; secret-scan refusal
  router.py        # classify(prompt) → capability; select(members, capability) → Member
  client.py        # async single-member call through the proxy (typed errors)
  fanout.py        # parallel fan-out: per-member RPM semaphore + timeout + quorum
  aggregate.py     # adaptive judge-synthesis | majority-vote
  orchestrator.py  # ask() and council() entrypoints
mcp/
  __init__.py
  server.py        # MCP server exposing `ask` + `council`
scripts/
  council-smoke.py # live end-to-end smoke (dev), like Phase 0's healthcheck
```

## 4. Data types & interfaces

```python
@dataclass(frozen=True)
class Member:
    alias: str            # e.g. "council/cerebras-glm-4.7"
    privacy_tier: str     # "A" | "B"
    capabilities: tuple[str, ...]  # subset of {"reasoning","code","fast","general"}
    strength: int         # 1..5
    rpm: int              # client-side semaphore size (default 10 if unset in config)

@dataclass(frozen=True)
class MemberAnswer:
    alias: str
    ok: bool
    answer: str | None    # None when the member abstained (429/timeout/error)
    detail: str           # "ok" | "timeout" | "429 rate-limited" | "HTTP n" | ...

@dataclass(frozen=True)
class AskResult:
    answer: str
    model_used: str
    capability: str | None   # None when a direct model was used
    note: str                # short trace, e.g. "auto-routed: reasoning → strength 5"

@dataclass(frozen=True)
class CouncilResult:
    answer: str
    per_member: list[MemberAnswer]
    disagreements: str       # judge's note, or "" for vote mode
    judge_used: str | None   # alias of the chair, or None for vote mode
    mode: str                # "judge" | "vote"
```

Typed errors (in `council/errors.py`, imported where raised): `PrivacyRefusal`
(secret detected, or no member satisfies the tier), `NoEligibleMember` (no member has
the requested capability), `AllMembersFailed` (every fan-out member abstained).

**Module interfaces:**
- `registry.load_members(config_path) -> list[Member]` — parse `model_list`; read
  `model_info.privacy_tier/capabilities/strength` and `litellm_params.rpm`.
- `privacy.scan_secrets(prompt) -> None` — raise `PrivacyRefusal` on a secret pattern.
- `privacy.allowed_members(members, sensitivity) -> list[Member]` — `sensitive` → tier A
  only; `public` → A+B.
- `router.classify(prompt, classifier: AsyncCaller) -> str` — return a capability label.
- `router.select(members, capability) -> Member` — highest `strength` having the
  capability; tie-break: higher `rpm` (faster). Raise `NoEligibleMember` if none.
- `client.complete(base_url, api_key, alias, prompt, *, max_tokens, timeout) -> str` —
  one proxy call; map 401/429/timeout/other to typed outcomes.
- `fanout.fan_out(prompt, members, caller, *, timeout=30) -> list[MemberAnswer]` —
  gather with per-member `asyncio.Semaphore(rpm)` and a per-member timeout; a member that
  429s/times out yields `MemberAnswer(ok=False, answer=None, ...)`; never raises for a
  single failure. Latency is bounded by `timeout`; early-quorum cancellation of stragglers
  is a deferred optimization.
- `aggregate.aggregate(prompt, answers, judge: AsyncCaller) -> (answer, mode,
  disagreements)` — pick vote vs judge (see §6); raise `AllMembersFailed` if no `ok`
  answers.
- `orchestrator.ask(prompt, *, model=None, capability=None, sensitivity="sensitive")
  -> AskResult`
- `orchestrator.council(prompt, *, members=None, sensitivity="sensitive")
  -> CouncilResult`

`AsyncCaller` is a thin callable `(alias, prompt) -> Awaitable[str]` backed by
`client.complete` — injected so tests can supply a fake (no live proxy).

## 5. Member registry & capability tags

Extend each `model_info` block in `proxy/config.yaml` with `capabilities` and
`strength` (additive — Phase-0 tests still pass). Starter values (estimates, tunable):

| alias | strength | capabilities |
|---|---|---|
| council/cerebras-glm-4.7 | 5 | reasoning, general, code |
| council/groq-gpt-oss-120b | 4 | reasoning, code, general, fast |
| council/cerebras-gpt-oss-120b | 4 | reasoning, code, general |
| council/groq-llama-70b | 3 | general, fast, code |
| council/cloudflare-llama-70b | 3 | general, fast |

Capability vocabulary for Phase 1: `{reasoning, code, fast, general}` (YAGNI — no
`vision`/`long_context` until a model/need exists). A member with no `capabilities`
defaults to `("general",)`; missing `strength` defaults to `1`.

## 6. `ask` and `council` behavior

### `ask(prompt, model?, capability?, sensitivity=sensitive)`
1. `scan_secrets(prompt)` → refuse on hit.
2. `allowed = allowed_members(all, sensitivity)`.
3. Selection:
   - `model` given → that member (must be in `allowed`, else `PrivacyRefusal`); no
     classify call.
   - else `capability` given → `select(allowed, capability)` (fast-path, no classify).
   - else → `capability = classify(prompt, classifier)` then `select(...)`.
4. `answer = client.complete(...)`; return `AskResult`.

**Classifier** = the fastest member, default `council/groq-llama-70b`, called with a
tiny prompt that constrains output to one of `{reasoning, code, fast, general}` and
`max_tokens` small. Configurable.

### `council(prompt, members?, sensitivity=sensitive)`
1. `scan_secrets` → refuse on hit.
2. `allowed = allowed_members(all, sensitivity)`; `members` defaults to the
   **provider-diverse trio** `{council/cerebras-glm-4.7, council/groq-gpt-oss-120b,
   council/cloudflare-llama-70b}` intersected with `allowed`.
3. `answers = fan_out(prompt, members, caller, timeout=30)` — parallel, per member
   `Semaphore(rpm)`, per-member timeout; 429/timeout ⇒ that member abstains. Aggregate
   proceeds with whoever returned; `AllMembersFailed` only if none did.
4. `aggregate(...)`:
   - **vote** when every `ok` answer is short/closed-form (matches a yes|no or a single
     option token after normalization) → majority label, `mode="vote"`, no extra call.
   - **judge** otherwise → chair `council/cerebras-glm-4.7` gets the K answers + a rubric
     ("produce the best merged answer; note disagreements") → `mode="judge"`.
5. Return `CouncilResult`.

Chair and default members are configurable constants in `orchestrator.py`.

## 7. Privacy gate (core safety)

- `sensitivity ∈ {sensitive, public}`, default **sensitive** (safe). Claude sets it —
  it knows whether the prompt carries repo code/internal data.
- `sensitive` → Tier-A members only; `public` → A+B. All members are Tier-A today, so
  the filter is a no-op now but **enforced** for when Tier-B arrives (Phase 3).
- **Secret-scan refusal (defense-in-depth):** before any outbound call, scan the prompt
  for high-confidence secret shapes — `sk-…`, `csk-…`, `gsk_…`, `-----BEGIN [A-Z ]*PRIVATE
  KEY-----`, and `AWS`/generic `*_API_KEY=`/`*_SECRET=` assignment lines. On a hit, raise
  `PrivacyRefusal` with a message telling the caller to strip secrets. Conservative
  patterns only (low false-positive); this directly serves CLAUDE.md's hard rule
  "secrets → NEVER to ANY free tier."

## 8. MCP server & usage protocol

- `mcp/server.py` — MCP Python SDK, stdio transport. Loads `LITELLM_MASTER_KEY` from
  `~/.config/consilium/.env` (or the environment); the proxy base URL defaults to
  `http://127.0.0.1:4000/v1`. Registered globally: `claude mcp add --scope user
  consilium -- <run command>`. Never logs the master key or prompts (prompts only at
  debug, and only for Tier-A targets, per CLAUDE.md).
- Two tools:
  - `ask(prompt, model?, capability?, sensitivity?)` → `AskResult` fields as text/JSON.
  - `council(prompt, sensitivity?)` → `CouncilResult` fields (merged answer +
    per-member + disagreements + judge).
- A dead proxy or dead member **degrades** (member abstains; a tool returns a clear
  error) — never crashes the caller's session.
- **Usage rule** appended to `~/.claude/CLAUDE.md` (the "protocol"): the council is a
  *second opinion, not the driver*; use `ask` for a quick routed second opinion, `council`
  for high-stakes cross-checks; always set `sensitivity` (default sensitive; never send
  secrets); rate-limit hygiene (prefer `ask`; reserve `council` for when diversity
  matters).

## 9. Error handling

- Errors are explicit/typed; no silent failures (CLAUDE.md).
- A single dead provider drops that voter (abstain), never crashes the council.
- `PrivacyRefusal` / `NoEligibleMember` / `AllMembersFailed` surface as clear tool
  errors, not stack traces.
- Secrets never logged; prompts logged only at debug and only for Tier-A targets.

## 10. Testing & the hard gate

CI-safe unit tests (no live keys — inject a fake `AsyncCaller` / `httpx.MockTransport`):
- `registry`: parses the 5 members with tier/capabilities/strength/rpm; defaults applied.
- `privacy`: tier filter (sensitive vs public); secret-scan refuses each pattern and
  passes clean prompts.
- `router`: `select` picks highest-strength member per capability, tie-break by rpm,
  raises `NoEligibleMember`; `classify` maps a fake classifier's label.
- `client`: 200/401/429/timeout mapping (MockTransport).
- `fanout`: one abstaining member still yields a usable result set; all-abstain →
  `AllMembersFailed` surfaces; per-member semaphore respected; never raises on a single
  member failure.
- `aggregate`: vote path on closed-form fixtures; judge path on open-ended (fake judge);
  `AllMembersFailed` when no ok answers.
- `orchestrator`: `ask` direct/capability/auto paths; `council` end-to-end with fakes.

Live `scripts/council-smoke.py` — a manual real fan-out against the running proxy (like
Phase 0's healthcheck), not part of CI. Hard gate: `ruff` clean + `pytest` green.

## 11. Acceptance criteria

- `ask` with no args auto-routes (classify → select → answer) and reports the model used;
  `ask(model=…)` and `ask(capability=…)` skip the classify call.
- `council` fans out to the default trio, aggregates adaptively (judge or vote), and
  returns per-member answers + disagreements; one dead member does not fail the call.
- Privacy gate: a `sensitive` prompt never selects a non-Tier-A member; a secret-shaped
  prompt is refused before any outbound call.
- The MCP server exposes `ask` and `council` and works when added `--scope user`; the
  usage rule is appended to `~/.claude/CLAUDE.md`.
- `ruff` clean and `pytest` green with no keys present; live smoke passes with the proxy
  up and keys in `~/.config/consilium/.env`.
- No secret in any tracked file, log line, or config.

## 12. Open notes (non-blocking)

- Capability tags and `strength` are first estimates; tune after real use.
- Classifier and chair models are configurable constants; revisit if Groq/ Cerebras
  limits bite.
- Debate (1-round) aggregation and Tier-B members are deferred to later phases.

## 13. Resilience — rate-limit fallback (sub-wave 1c)

Free tiers 429 often (Cerebras ~5 RPM was hit repeatedly during the live 1a smoke).
A limit-hit already becomes a typed `MemberCallError("429 rate-limited")` at the client,
and in `council` a fan-out member that 429s simply abstains. Two gaps remain, closed here:

**A. `ask` fallback (auto/capability modes only).**
- `router.rank(members, capability) -> list[Member]` returns every eligible member sorted
  by `(strength, rpm)` descending (raises `NoEligibleMember` if none). `select` becomes
  `rank(...)[0]`.
- `Orchestrator.ask` iterates the ranked candidates: on `MemberCallError` from one, it
  records the failure and tries the next; the first success returns, with the fallback
  trail in `note` (e.g. `auto-routed: reasoning -> glm-4.7[429 rate-limited] -> groq-gpt-oss-120b`).
  If every candidate fails → `AllMembersFailed`.
- **Direct `model=` does NOT fall back** — naming a model means you want that model; its
  failure surfaces as the typed error.

**B. Judge fallback (`council`).**
- `aggregate.aggregate(prompt, answers, *, caller, judge_aliases: list[str]) ->
  (answer, mode, disagreements, judge_used)` (was a 3-tuple with a single `judge_alias`).
  It tries each judge alias in order; the first success → `mode="judge"`, `judge_used=<alias>`.
  If **every** judge call fails → **best-single fallback**: return the most substantive ok
  answer (`max(ok, key=len)`), `mode="best-single"`, `judge_used=None`. Vote path unchanged
  (`mode="vote"`, `judge_used=None`).
- `Orchestrator.council` builds the judge order = chair first, then the remaining chosen
  members by descending `strength`, and passes it to `aggregate`. `CouncilResult.mode` is
  now one of `{"vote","judge","best-single"}`.

Deferred to Phase 2 (deployment hardening): exponential backoff on 429, per-member RPD
counters + daily rotation, quota telemetry.

## 14. Phase map (orientation)

The original SUPERPROMPT numbered phases 0–3 with Phase 1 = council and Phase 2 = MCP.
Shipping MCP immediately merged those into a single **Phase 1**, so the numbering is
re-based:

- **Phase 0 — Compute** ✅ (proxy + 3 Tier-A providers; merged to `main`, pushed).
- **Phase 1 — Council + MCP** (this spec): sub-waves 1a engine · 1b MCP + protocol · 1c
  resilience.
- **Phase 2 — Deployment hardening** (formerly Phase 3): systemd always-on, RPD/quota
  telemetry + rotation, backoff, additional providers (incl. Tier-B under the gate).

CLAUDE.md / SUPERPROMPT phase wording is reconciled to this map in sub-wave 1b's docs task.
