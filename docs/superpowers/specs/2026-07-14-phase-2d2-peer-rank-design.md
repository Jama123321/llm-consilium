# Phase 2d-2 — Peer-Rank Mode (design/spec)

> Status: approved for planning (2026-07-14). Next: writing-plans.
> Second sub-wave of the Phase 2d council-quality sprint (after 2d-1 core synthesis,
> before 2d-3 debate). Reuses 2d-1's `anonymize` + `AggregateResult`.

## Business context

The council currently reduces answers by chair-synthesis (`judge`) or majority (`vote`).
Both put one model (or word-counting) in charge of picking the truth. Peer-rank adds a
democratic alternative: every member ranks the anonymized answers and the winner is the
one the group collectively rates highest — a different, often more objective reducer for
contentious or judgment questions. It reuses 2d-1's anonymization (kills brand/position
bias) and adds self-vote exclusion so a member can't crown its own answer.

## Goal

Add a `peer-rank` aggregation mode (pick-best-verbatim, self-vote excluded) selectable via
an explicit `mode` argument, plus the `mode` plumbing through `aggregate` → `council` →
MCP. Auto behaviour (no `mode`) is unchanged (vote/judge).

## Global Constraints (verbatim, apply to every task)

- Peer-rank returns the top-ranked member answer **verbatim** — no synthesis (synthesis of
  top-N is a possible later refinement, out of scope here).
- **Self-vote exclusion is mandatory:** a member's ranking never counts toward the score of
  its own answer.
- Auto mode (no `mode` given) is byte-for-byte the current vote/judge behaviour.
- Reused/borrowed design (karpathy peer-rank — **no license → reimplemented from the design
  only**, with self-vote exclusion added); a credit comment names the idea.
- Determinism: anonymization and any shuffle take an injectable `random.Random`; ranker
  replies are scripted in tests. No real model calls in tests.
- Graceful degradation: a ranker whose call fails or whose ranking is unparseable is
  dropped; if fewer than 2 valid rankers remain, peer-rank falls back to `judge`.
- Python 3.10+; `ruff check .` clean + `pytest -q` green. Commits English imperative, no
  `Co-Authored-By`. Branch `phase-2d2-peer-rank` (off `main`, which now has 2c + 2d-1).

## 1. Anonymization mapping — `council/anonymize.py`

Peer-rank needs to know which code-name belongs to which member (to exclude self-votes),
which 2d-1's `anonymize` intentionally dropped.

- Add `anonymize_pairs(pairs: list[tuple[str, str]], *, rng: random.Random | None = None)
  -> tuple[str, list[tuple[str, str]]]` — `pairs` are `(owner, text)`; shuffles them with
  the injected rng, assigns block-order code-names, returns `(labeled_block, mapping)`
  where `mapping[i] = (codename_i, owner_i)` aligned to the block. Raises `ValueError` when
  `len(pairs) > len(CODE_NAMES)`.
- Refactor the existing `anonymize(answers, *, rng)` to delegate:
  `block, mapping = anonymize_pairs([("", a) for a in answers], rng=rng); return block,
  [cn for cn, _ in mapping]` — same output contract as 2d-1, shuffle logic lives once.

## 2. Peer-rank — `council/aggregate.py`

- `_RANK_PROMPT` (reimplemented design; credit comment: karpathy llm-council): "Below are
  anonymized candidate answers labelled by code-name. Rank them best-to-worst by
  correctness and completeness; do not favour any particular one. End with exactly one
  line: `RANKING: <Name>, <Name>, …` listing every code-name, best first."
- `_parse_ranking(reply: str, valid: list[str]) -> list[str]` — extract the `RANKING:` line
  (case-insensitive), return the code-names found there, in order, filtered to `valid`,
  de-duplicated. Missing code-names are treated as tied-last by the scorer (not appended
  here). Empty/absent → `[]` (ranker dropped).
- `async def _peer_rank(prompt, ok_members: list[MemberAnswer], *, caller, rng)
  -> AggregateResult`:
  1. `pairs = [(a.alias, a.answer) for a in ok_members]`; `block, mapping =
     anonymize_pairs(pairs, rng=rng)`; `owner_of = {codename: owner}`;
     `answer_of_codename = {codename: answer}` (via mapping order ↔ shuffled pairs).
  2. Fan out ranking calls to every member **in parallel** (`asyncio.gather`), each getting
     `_RANK_PROMPT` with `block`; per-ranker failure (`MemberCallError`/timeout/other) →
     dropped. Collect `rankings: dict[ranker_alias, list[codename]]` for parseable replies.
  3. If `< 2` valid rankings → return the judge path result (call the judge fallback).
  4. **Mean-ordinal with self-vote exclusion:** for each candidate code-name `c` (owned by
     `o`), average its rank position across all rankings **except** ranker `o`'s; a ranking
     that omits `c` contributes `len(candidates)` (tied-last) for `c`. Lowest mean wins;
     ties broken by more first-place (non-self) votes, then by code-name order.
  5. `confidence`: `high` if the winner is ranked first by a majority of its non-self
     rankers; `medium` if it has the best mean but not that majority; `low` otherwise.
  6. Return `AggregateResult(answer=answer_of_codename[winner], mode="peer-rank",
     disagreements="", judge_used=None, confidence=…)`.

## 3. Mode selection — `council/aggregate.py`

- `aggregate(prompt, answers, *, caller, judge_aliases, rng=None, mode: str | None = None)`:
  - `mode is None` → current auto: closed-form → `vote`, else `judge`.
  - `mode == "vote"` → force `_majority` path (vote).
  - `mode == "judge"` → force the judge path (skip closed-form vote).
  - `mode == "peer-rank"` → `_peer_rank(...)` (with the judge path as its degradation
    fallback).
  - unknown `mode` → `ValueError` (explicit, typed).
- The `ok`/all-abstain guard runs first regardless of mode.

## 4. Wiring

- `council/orchestrator.py` — `council(prompt, *, members=None, size=None, mode=None,
  sensitivity="sensitive")` passes `mode` into `aggregate(...)`. Rankers for peer-rank are
  the council members already fanned out (from `answers`), so no extra roster is needed.
- `consilium_mcp/server.py` — MCP `council` gains a `mode` param, documented in the
  docstring (values: auto default, `"judge"`, `"vote"`, `"peer-rank"`).
- `docs/usage-rule.md` — note the `mode` argument and when peer-rank helps.

## 5. Testing

- **anonymize_pairs**: mapping aligns code-name↔owner; `anonymize` delegates and keeps its
  2d-1 output contract (parity test); `ValueError` when over `CODE_NAMES`.
- **_parse_ranking**: full ranking, partial (missing names), malformed/absent, duplicates,
  case-insensitive marker.
- **_peer_rank** (seeded rng + scripted ranker replies): mean-ordinal winner; **self-vote
  exclusion changes the winner** (a member ranking itself first must not let it win);
  degradation to judge when < 2 valid rankers; confidence high/medium/low cases.
- **mode routing**: `aggregate(mode="peer-rank"/"judge"/"vote")` takes the right path;
  unknown mode raises `ValueError`; `mode=None` unchanged.
- **passthrough**: `Orchestrator.council(mode="peer-rank")` and MCP `council(mode=…)`
  reach aggregate; `AggregateResult.mode` surfaces on `CouncilResult.mode`.

## 6. Out of scope (explicit)

- Debate (stance/PROPOSE-CHALLENGE-REVISE), convergence early-exit, adversarial-rigor
  confidence → **2d-3**.
- Auto-routing that *chooses* peer-rank without an explicit `mode` → deferred (unclear
  heuristic; revisit after debate lands).
- Rank-then-synthesize (top-N → chair) → deferred refinement.

## 7. Files

- `council/anonymize.py` — `anonymize_pairs`; `anonymize` delegates.
- `council/aggregate.py` — `_RANK_PROMPT`, `_parse_ranking`, `_peer_rank`, `mode` param.
- `council/orchestrator.py` — `council` gains `mode`, passes it through.
- `consilium_mcp/server.py` — MCP `council` gains `mode` + docstring.
- `docs/usage-rule.md` — document `mode`.
- Tests: `tests/test_anonymize.py`, `tests/test_aggregate.py`, `tests/test_orchestrator.py`,
  `tests/test_mcp_server.py`.
