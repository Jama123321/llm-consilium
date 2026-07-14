# Phase 2d-1 — Core Synthesis Quality (design/spec)

> Status: approved for planning (2026-07-14). Next: writing-plans.
> Part of the Phase 2d council-quality sprint, decomposed into sub-waves:
> **2d-1 (this) = anonymization + Fusion judge + confidence**, then 2d-2 (peer-rank mode),
> then 2d-3 (debate mode). 2d-1 is the foundation the later modes reuse.

## Business context

The council already fans out to diverse models and a chair synthesizes the answers,
but the synthesis path has two known quality leaks: candidates are labelled `[1] [2]`
(positional bias — judges favour the first) and carry no debiasing instruction (brand/
style bias — a judge that is itself a council member can favour its own answer), and the
judge prompt is a thin "merge these" that invites averaging rather than reasoning. 2d-1
fixes both cheaply and adds a confidence signal, improving every council synthesis with
no new modes and no extra model calls.

## Goal

Upgrade the existing `judge`/`vote` aggregation: anonymize candidates with shuffled
code-names (kills positional + brand bias), replace the judge prompt with a Fusion-style
"reason, don't average, rewrite standalone" prompt, and surface a categorical
`confidence` (high/medium/low) on every `CouncilResult`.

## Global Constraints (verbatim, apply to every task)

- No new aggregation modes in 2d-1 — only the existing `vote` and `judge` paths change.
  Peer-rank and debate are 2d-2 / 2d-3.
- No extra model calls added — anonymization and confidence piggyback on the single
  existing judge call; the `vote` path derives confidence locally.
- Borrowed designs (ai-council code-names/synthesis, FreeLLMAPI Fusion prompt — both MIT)
  are **reimplemented** in our own wording/list, not copied verbatim; a short credit
  comment names the source idea. The repo stays cleanly MIT-shareable (no NOTICE needed).
- Determinism: anonymization takes an injectable `random.Random` so tests are hermetic.
- Privacy gate, tiering, and the council roster (2c) are unchanged.
- Python 3.10+. `ruff check .` clean + `pytest -q` green. Commits English imperative,
  no `Co-Authored-By`. Branch `phase-2d-council-quality` (off 2c).

## 1. Anonymization primitive — `council/anonymize.py` (new)

A small pure module reused by 2d-2/2d-3.

- `CODE_NAMES: tuple[str, ...]` — a fixed list of ~12 neutral, distinct names
  (e.g. Aardvark, Basilisk, Cheetah, …). Our own list; credit comment references the
  ai-council code-name idea (MIT).
- `anonymize(answers: list[str], *, rng: random.Random | None = None) -> tuple[str, list[str]]`
  - shuffles the answer order (using `rng or random.Random()`), assigns each a code-name
    from `CODE_NAMES` in order, and returns `(labeled_block, codenames)` where
    `labeled_block` is `"<Name>:\n<answer>\n\n<Name>:\n<answer>…"` and `codenames` is the
    code-name list in the shuffled order (index-aligned to the block).
  - raises `ValueError` if `len(answers) > len(CODE_NAMES)` (K ≤ 12 in practice; council
    size is 3-5, so this is a guard, not a real limit).
  - the returned mapping lets callers relate a code-name back to its answer if needed;
    the judge never sees model aliases or positions.

## 2. Fusion judge prompt — `council/aggregate.py`

Replace `_JUDGE_PROMPT` with a Fusion-style prompt (our wording; credit comment
references FreeLLMAPI Fusion, MIT):

- Candidates presented via the anonymized `labeled_block` (code-names, shuffled).
- Instruction: "You are the chair. Several council members answered independently
  (labelled by code-name — you do not know which is which, weight them equally).
  Synthesize the single best **standalone** answer. Reason about which claims are
  correct; **do not average or split the difference**, and **never refer to a member by
  code-name or number** in your answer."
- Trailer contract: the model appends two lines —
  `DISAGREEMENTS: <where members differed, or 'none'>` and
  `CONFIDENCE: <high|medium|low>` (its confidence the synthesized answer is correct).

## 3. Confidence + `AggregateResult` — `council/types.py`, `council/aggregate.py`

- Replace `aggregate()`'s 4-tuple return with a frozen dataclass
  `AggregateResult(answer: str, mode: str, disagreements: str, judge_used: str | None,
  confidence: str)` (`confidence` ∈ {"high","medium","low",""} — "" = unknown).
- `CouncilResult` gains `confidence: str = ""` (last field, default keeps existing
  construction valid).
- **Judge path:** parse the `CONFIDENCE:` line (case-insensitive, normalized to
  high/medium/low; unparseable → ""). Parse `DISAGREEMENTS:` as today.
- **Vote path:** derive confidence from agreement — all answers equal → "high";
  strict majority (> half) → "medium"; only a plurality → "low".
- **best-single fallback:** confidence "" (no basis).

## 4. Wiring

- `council/orchestrator.py` — `council` unpacks `AggregateResult` and passes
  `confidence` into `CouncilResult`. (Only the aggregate call site changes.)
- `consilium_mcp/server.py` — `_shape_council` adds `"confidence": r.confidence`.
- `docs/usage-rule.md` — note that `council` returns a `confidence` field.

## 5. Testing

- **anonymize** (seeded `random.Random(0)`): correct code-names assigned, order shuffled
  vs input, mapping index-aligned, block format, `ValueError` when answers exceed
  `CODE_NAMES`.
- **judge prompt**: the prompt fed to the judge contains code-names and NOT `[1]`/model
  aliases (assert on the captured caller prompt); parses answer/disagreements/confidence
  from a mocked judge reply; unparseable confidence → "".
- **vote confidence**: unanimous → "high", majority → "medium", plurality → "low".
- **orchestrator passthrough**: `CouncilResult.confidence` is populated end-to-end.
- **MCP shape**: `_shape_council` includes `confidence`.

## 6. Out of scope (explicit)

- Peer-rank mode, mode selection/override → **2d-2**.
- Stance/debate, convergence early-exit, adversarial-rigor confidence → **2d-3**.
- Changing the vote-vs-judge auto-routing threshold (`_looks_closed_form`) — unchanged.

## 7. Files

- `council/anonymize.py` — NEW: `CODE_NAMES`, `anonymize`.
- `council/aggregate.py` — Fusion prompt, anonymized candidates, confidence parse/derive,
  return `AggregateResult`.
- `council/types.py` — `AggregateResult`; `CouncilResult.confidence`.
- `council/orchestrator.py` — unpack `AggregateResult` at the aggregate call site.
- `consilium_mcp/server.py` — `_shape_council` adds `confidence`.
- `docs/usage-rule.md` — document the `confidence` field.
- Tests: `tests/test_anonymize.py` (new), `tests/test_aggregate.py`,
  `tests/test_orchestrator.py`, `tests/test_mcp_server.py`.
