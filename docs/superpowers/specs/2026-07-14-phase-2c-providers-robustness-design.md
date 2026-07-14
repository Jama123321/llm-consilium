# Phase 2c — Providers + Rate-limit Robustness (design/spec)

> Status: approved for planning (2026-07-14). Next: writing-plans.
> Business context: 2c makes the council **stronger** (more + more-diverse members,
> incl. a GPT-class Tier-A model) and **cheaper/steadier to run** (native LiteLLM
> failover + key-presence activation). It does **not** touch aggregation logic —
> that is Phase 2d. Boundary kept deliberately thin to avoid 2c/2d merge conflicts.

## Goal

Grow the model pool from 5 to up to 13 members across 7 provider families, give every
model a per-capability "dossier", make the council roster **dynamic** (capability-aware,
adaptive size, vendor-diverse) with a **manual override**, and harden operation with
LiteLLM-native rate-limit config and key-presence activation — all under the existing
privacy gate, which stays a hard, non-bypassable safety rule.

## Global Constraints (verbatim, apply to every task)

- **Privacy tiering is a hard gate.** `sensitive` prompt → **Tier-A members only**.
  Tier-B (`privacy_tier: B`) is reachable **only** by `public` prompts. This holds on
  **every** path including manual roster selection — a manually-requested Tier-B member
  on a `sensitive` prompt is **dropped, never called** (recorded in a note).
- **Secrets only in `~/.config/consilium/.env`** (chmod 600). Never in code, git, logs,
  or memory. Provider keys are referenced via `os.environ/*` in `proxy/config.yaml`.
- **Tier verdicts** (from research, corrected): GitHub Models = **A**; Mistral,
  SambaNova, NVIDIA NIM = **B**. Tier follows the **inference provider**, not the
  weights' origin (a Llama served by GitHub Models is Tier-A because GitHub's ToS says
  no-train).
- Python 3.10+, `ruff` clean + `pytest` green is the hard gate. No `Co-Authored-By`.
- Exact model IDs and free-tier limits **drift** — re-verify live at implementation
  (as we had to for Cerebras), then encode as `rpm`/`rpd`/`tpd`.

## 1. Provider catalog (2 models per new provider)

Add 8 aliases (2 × 4 providers) to `proxy/config.yaml`. IDs below are provisional —
verify against each provider's live `/models` at implementation.

| provider_family | alias | primary direction | tier | key env var |
|---|---|---|---|---|
| github | `council/github-gpt-4.1` | general/code | **A** | `GITHUB_API_KEY` |
| github | `council/github-o4-mini` | reasoning/fast | **A** | `GITHUB_API_KEY` |
| mistral | `council/mistral-large` | reasoning/general | B | `MISTRAL_API_KEY` |
| mistral | `council/mistral-codestral` | code/fast | B | `MISTRAL_API_KEY` |
| sambanova | `council/sambanova-llama-405b` | reasoning/general | B | `SAMBANOVA_API_KEY` |
| sambanova | `council/sambanova-llama-70b` | fast/general | B | `SAMBANOVA_API_KEY` |
| nvidia | `council/nvidia-deepseek-r1` | reasoning | B | `NVIDIA_NIM_API_KEY` |
| nvidia | `council/nvidia-llama-70b` | general/code/fast | B | `NVIDIA_NIM_API_KEY` |

Existing 5 Tier-A aliases stay. Result: **13 members** (7 Tier-A, 6 Tier-B).

**NVIDIA is added to config but its key is pending** (user lacks provider access). Via
key-presence activation (§4) the two NVIDIA aliases sit dormant until the key exists;
live-smoke (§8) covers only GitHub/Mistral/SambaNova this phase.

## 2. Dossier schema (`model_info`)

Replace the flat `strength` + `capabilities:[...]` with a per-capability score map plus
a family tag:

```yaml
model_info:
  privacy_tier: A                 # A | B  (default B if absent)
  provider_family: github         # optional; default derived from litellm model prefix
  scores:                         # capability -> 1..5; absent capability = not eligible
    reasoning: 5
    code: 4
    fast: 4
    general: 3
  rpd: 50                         # optional daily caps (unchanged semantics)
  tpd: 1000000
```

- Capabilities: `reasoning | code | fast | general` (unchanged vocabulary).
- **Backward compatibility:** if `scores` is absent but legacy `strength` (int) and
  `capabilities` (list) are present, registry synthesizes `scores = {cap: strength for
  cap in capabilities}`. Old-style entries remain valid; we migrate the 5 existing
  aliases to `scores` in the same task but the fallback must be tested.
- `provider_family`: if absent, derive from the litellm `model` prefix
  (`cerebras/…` → `cerebras`, `github/…` → `github`, `openai/@cf/…` → `cloudflare`,
  etc.). Explicit `provider_family` overrides.

`Member` gains `scores: dict[str, int]` and `provider_family: str`. Downstream code uses
`scores`; the old scalar `strength` is dropped from the type (synthesized only during
parsing for legacy configs).

## 3. Router (`ask`) — capability-score ranking

`rank(members, capability)`: eligible = members with `capability in scores`; sort by
`scores[capability]` desc, then `rpm` desc. `select = rank[0]`. For `capability` unset
or `general`, rank by `scores.get("general", max(scores.values()))`.

Effect: `ask(capability="code")` picks the highest `scores.code` (e.g. codestral beats a
stronger generalist). Manual `ask(model=...)` unchanged; still filtered by the gate.

## 4. Key-presence activation

A member whose referenced key env var is unset (or empty) is **inactive**: excluded
from the pool the router/council draw from. Not an error, not a failed call.

- Determined at registry load: for each member, resolve the env var name(s) its
  `litellm_params` reference via `os.environ/NAME`; if any required one is missing/empty,
  mark the member inactive.
- `load_members(...)` returns only active members by default; an internal
  `load_members(..., include_inactive=True)` supports introspection/tests.
- This cleanly handles NVIDIA-pending and pre-stages Phase 3 (colleagues with partial
  key sets get a working subset, not startup failures).

## 5. Council composition

Three roster paths; the **privacy gate + usage filter run on all of them**.

- **Manual:** `council(prompt, members=[...])` uses exactly those aliases, then
  filters through the gate (`sensitive` drops Tier-B) and usage-exhaustion. `K = len`
  after filtering. Unknown alias → dropped with a note (no crash). If the filtered
  roster is empty → fall back to auto-compose within the allowed tier + note.
- **Auto:** classify the prompt once (reuse `router.classify`, classifier kept inside
  the allowed tier via existing `_classifier_for`) → dominant capability → adaptive `K`
  → `compose_council`.
- **Adaptive K** (default, overridable by explicit `size=`):
  `fast` → 3, `code` → 4, `general` → 4, `reasoning` → 5. Clamp to available members.
- **`compose_council(members, *, k, capability)`** — greedy vendor-diverse top-K:
  1. score each eligible member by `scores.get(capability, max(scores.values()))`;
  2. sort by score desc, `rpm` desc;
  3. pass 1 — pick the top member of each **distinct** `provider_family` until K or
     families exhausted; pass 2 — fill remaining slots by score regardless of family.
  Yields "K strongest in this direction, spread across vendors" → decorrelated errors.

`DEFAULT_MEMBER_ALIASES` (the fixed trio) is removed; composition replaces it. Chair /
judge selection stays inside the allowed tier (existing `_judge_order`). Aggregation
logic is untouched (Phase 2d).

## 6. MCP ergonomics (self-documenting tools)

The calling model (and a human reading the rule) must understand every parameter without
guessing. FastMCP builds the tool schema from the signature + docstring, so:

- `ask(prompt, model=None, capability=None, sensitivity="sensitive")` and
  `council(prompt, sensitivity="sensitive", members=None, size=None)` each carry a
  docstring documenting **every** parameter: purpose, allowed values, default, and — for
  `sensitivity` and `members` — an explicit privacy note ("Tier-B is dropped on
  sensitive prompts").
- Clear names: `members` = explicit roster (list of member aliases); `size` = council
  size override. Enumerate `capability` values (`reasoning|code|fast|general`).
- Return shapes stay structured and stable (`ask` → answer/model_used/capability/note;
  `council` → answer/per_member/disagreements/judge_used/mode). Notes surface what the
  system decided (dropped members, degraded roster, fallbacks).
- Update `docs/usage-rule.md` (the `~/.claude/CLAUDE.md` block) to describe the new
  `members`/`size` params and the manual-vs-auto roster behaviour in human terms.

## 7. Rate-limit robustness (LiteLLM-native)

Configure in `proxy/config.yaml` `router_settings` — **complements**, does not replace,
our 2b usage-store daily rotation (proxy handles per-request retry/failover/cooldown;
usage-store handles daily-cap rotation across sessions):

- per-deployment `allowed_fails` + `cooldown_time` (cool a flapping deployment);
- `retry_policy` per error class (retry timeouts/5xx, not 429/auth);
- `fallbacks: [{"council/X": ["council/Y", ...]}]` — same-tier, same-capability
  fallbacks only (a Tier-A model must never fall back to Tier-B);
- keep `num_retries`.

Fallback maps must respect tiers: **no Tier-A → Tier-B fallback ever**.

## 8. Testing

- **Unit:** `scores` parsing + legacy `strength/capabilities` synthesis; `provider_family`
  derivation + override; key-presence activation (missing var → inactive; present → active);
  router capability-score ranking (codestral wins on `code`); `compose_council` vendor
  diversity + adaptive K + clamp; manual roster filtering **including Tier-B dropped on
  sensitive even when explicitly requested**; unknown-alias drop; empty-roster fallback.
- **Live smoke** (`scripts/council-smoke.py` extension): 1-token ping to each active new
  alias (GitHub/Mistral/SambaNova — 6 aliases; NVIDIA skipped, no key); a **public**
  council that includes ≥1 Tier-B member; a **sensitive** council asserting **no** Tier-B
  member was contacted (`per_member` all Tier-A).

## 9. Errors

- Unknown manual alias → drop + note (never crash).
- Inactive (no-key) member → excluded silently (not an error).
- Dead/timeout provider → existing degrade-the-voter behaviour.
- Whole allowed tier exhausted → existing 2b behaviour (rotation, then best-effort).

## 10. Out of scope (explicit)

- Aggregation quality (anonymized synthesis, peer-rank, debate, convergence,
  confidence) → **Phase 2d**.
- `consilium init` wizard / path-agnostic installer / public README → **Phase 3**.
- ZDR toggles on Groq; multi-day usage history; cost/$ tracking → deferred backlog.

## 11. Files (anticipated)

- `proxy/config.yaml` — 8 new aliases + dossier migration of existing 5 + `router_settings`.
- `council/types.py` — `Member.scores`, `Member.provider_family`, drop scalar `strength`.
- `council/registry.py` — parse `scores`/`provider_family`, legacy synthesis, key-presence.
- `council/router.py` — capability-score `rank`; adaptive-K helper.
- `council/fanout.py` (or new `council/compose.py`) — `compose_council` vendor-diverse.
- `council/orchestrator.py` — wire manual/auto roster, adaptive K, key-presence pool.
- `consilium_mcp/server.py` — `council(members, size)` signature + docstrings.
- `scripts/run-proxy.sh` — validate new env vars **only if present** (no fail-fast on
  optional providers).
- `docs/usage-rule.md` — document new params.
- Tests across `tests/` for each unit above; `scripts/council-smoke.py` extension.
