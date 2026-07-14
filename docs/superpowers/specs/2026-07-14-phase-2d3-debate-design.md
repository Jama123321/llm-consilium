# Phase 2d-3 — Debate Mode (design/spec)

> Status: approved for planning (2026-07-14). Next: writing-plans.
> Final sub-wave of the Phase 2d council-quality sprint (after 2d-1 core synthesis and
> 2d-2 peer-rank). Reuses `anonymize_pairs`, `AggregateResult`, `_judge`, and the `mode`
> plumbing already threaded through `aggregate` → `council` → MCP.

## Business context

`judge` synthesizes and `peer-rank` votes, but neither forces the models to *challenge*
each other — so a confident-but-wrong consensus survives. Debate mode makes members
argue: each takes an assigned stance (for / against / neutral), critiques the anonymized
answers, and revises. Rounds repeat until the answers converge (or a cap is hit), then the
chair synthesizes. Confidence reflects how much adversarial scrutiny the answer survived.
This is the strongest reducer for contentious or high-stakes questions, at the cost of
more free-tier calls.

## Goal

Add a `debate` aggregation mode: bounded stance-steered CHALLENGE→REVISE rounds over the
anonymized answers with Jaccard convergence early-exit (cap 2 rounds), a Fusion synthesis
of the final revised answers, and a convergence-derived `confidence`. Selectable via
`mode="debate"`.

## Global Constraints (verbatim, apply to every task)

- Debate returns a **Fusion synthesis** of the final revised answers (reuses `_judge`),
  with `mode="debate"` and `judge_used` set to the synthesizing chair.
- **Max 2 CHALLENGE→REVISE rounds** (`max_rounds=2`), with early-exit when the revised
  answers converge. At least one full round runs before any exit.
- **Honesty guardrail (PAL):** the stance prompt must state "your stance is NOT a license
  to lie — flag only genuine errors." Stance steering assigns for/against/neutral
  round-robin to force disagreement.
- **Convergence** uses word-set Jaccard (DUH design, reimplemented — standard math): mean
  pairwise Jaccard of the current revised answers ≥ 0.7 → converged.
- **Confidence-as-rigor** (DUH, reimplemented): from the final mean pairwise Jaccard —
  ≥0.7 → high, ≥0.4 → medium, else low. Overrides the judge's own confidence.
- Reused/borrowed: PAL stance-steering is Apache-2.0 → reimplemented in our wording with a
  credit comment (we keep the repo MIT-shareable; no verbatim Apache file needed since we
  reimplement); DUH convergence/rigor is AGPL → reimplemented from the design (standard
  math). Credit comments name both.
- Determinism: `anonymize_pairs` and any shuffle take an injectable `random.Random`; debate
  replies are scripted in tests. No real model calls in tests.
- Degradation: a member whose CHALLENGE call fails or lacks a parseable `REVISED:` line
  keeps its prior answer; `< 2` usable answers → fall back to `_judge`.
- Auto mode (`mode is None`) and the existing `vote`/`judge`/`peer-rank` paths are
  unchanged. Python 3.10+; `ruff check .` clean + `pytest -q` green. Commits English
  imperative, no `Co-Authored-By`. Branch `phase-2d3-debate` (off `main`).

## 1. Convergence + revision helpers — `council/aggregate.py`

- `_words(s: str) -> list[str]` — lowercase word tokens (`re.findall(r"[a-z0-9]+", s.lower())`).
- `_jaccard(a: str, b: str) -> float` — `|Wa ∩ Wb| / |Wa ∪ Wb|`; both empty → 1.0; one empty → 0.0.
- `_mean_pairwise_jaccard(answers: list[str]) -> float` — mean of `_jaccard` over all unordered pairs; `< 2` answers → 1.0.
- `_parse_revision(reply: str) -> str | None` — text after a case-insensitive `REVISED:` marker (stripped); absent/empty → `None`.

## 2. Debate loop — `council/aggregate.py`

- `_STANCES = ("for", "against", "neutral")`.
- `_DEBATE_PROMPT` (reimplemented; credit comment: PAL stance-steering, Apache): states the
  member's assigned stance, explains for/against/neutral, includes the **"stance is not a
  license to lie — flag only genuine errors"** guardrail, presents the current anonymized
  answers, asks the member to critique from its stance and then give its own best revised
  answer, ending with exactly one line: `REVISED: <answer>`.
- `async def _debate(prompt, ok_members: list[MemberAnswer], *, caller, judge_aliases, rng,
  max_rounds: int = 2, threshold: float = 0.7, timeout: float = 30.0) -> AggregateResult`:
  1. If `len(ok_members) < 2` → return `_judge(prompt, [answers], ...)` (can't debate solo).
  2. `current = {alias: answer}` from `ok_members`; `aliases = [a.alias for a in ok_members]`.
  3. For up to `max_rounds` rounds:
     a. `block, _ = anonymize_pairs([(alias, current[alias]) for alias in aliases], rng=rng)`.
     b. Fan out CHALLENGE→REVISE **in parallel** (`asyncio.gather`): member `i` gets stance
        `_STANCES[i % 3]` and the `block`; per-member failure/timeout → `None` (keeps prior
        answer). Parse each reply with `_parse_revision`.
     c. Apply revisions: `current[alias] = revised` where `revised` is not `None`.
     d. `conv = _mean_pairwise_jaccard(list(current.values()))`; if `conv >= threshold` →
        break.
  4. `confidence` = high/medium/low from the final `conv` (≥0.7 / ≥0.4 / else).
  5. `judged = await _judge(prompt, list(current.values()), caller=caller,
     judge_aliases=judge_aliases, rng=rng)`.
  6. Return `AggregateResult(judged.answer, "debate", judged.disagreements,
     judged.judge_used, confidence)`.

## 3. Mode dispatch — `council/aggregate.py`

Add to `aggregate`'s dispatch: `if mode == "debate": return await _debate(prompt,
ok_members, caller=caller, judge_aliases=judge_aliases, rng=rng)`. All other modes and the
`None`-auto path are unchanged. `Orchestrator.council` needs NO change — `mode` is already
threaded generically.

## 4. Surface — `consilium_mcp/server.py`, `docs/usage-rule.md`

- MCP `council` docstring: add `"debate"` to the `mode` values with a one-line description
  ("members debate under assigned stances and converge; strongest for contentious
  questions, most free-tier calls").
- `docs/usage-rule.md`: extend the `mode` note to mention `"debate"`.

## 5. Testing

- **helpers**: `_jaccard` (identical→1.0, disjoint→0.0, known partial value, empty cases);
  `_mean_pairwise_jaccard` (single→1.0, multi); `_parse_revision` (present multi-word,
  absent→None, case-insensitive).
- **stance assignment**: a council of 3 with a prompt-capturing caller → the three debate
  prompts carry stances `for`, `against`, `neutral` (round-robin).
- **convergence early-exit**: scripted callers whose revisions are identical → converge in
  round 1; assert the debate issued only ~K challenge calls + 1 synthesis (not 2K), i.e. it
  stopped early.
- **no early convergence**: divergent revisions → runs the full 2 rounds, then synthesizes;
  `confidence == "low"` (or medium) from low final Jaccard.
- **degradation**: `< 2` members → `_judge` (mode "judge"); a failing challenger keeps its
  prior answer (assert its prior text still participates in synthesis).
- **confidence-as-rigor**: converged answers → `confidence == "high"`; divergent → low.
- **final synthesis**: `_judge` is called on the final revised answers; result `mode ==
  "debate"`, `judge_used` is the chair, answer is the judge's merge.
- **mode routing**: `aggregate(mode="debate")` → `_debate`; `mode="peer-rank"/"judge"/
  "vote"/None` unchanged; unknown → `ValueError`.
- **MCP**: `council(mode="debate")` reaches the orchestrator (FakeOrch capturing kwargs).

## 6. Out of scope (explicit)

- Unbounded rounds / round-count > 2, per-domain confidence caps, and full DUH state-machine
  framings beyond for/against/neutral → not now (revisit if debate proves valuable).
- Auto-routing that *chooses* debate without explicit `mode` → deferred.
- Changing `judge`/`peer-rank`/`vote` behaviour.

## 7. Files

- `council/aggregate.py` — `_words`/`_jaccard`/`_mean_pairwise_jaccard`/`_parse_revision`,
  `_STANCES`/`_DEBATE_PROMPT`/`_debate`, `mode == "debate"` dispatch.
- `consilium_mcp/server.py` — `council` docstring adds `"debate"`.
- `docs/usage-rule.md` — `mode` note adds `"debate"`.
- Tests: `tests/test_aggregate.py`, `tests/test_mcp_server.py`.
