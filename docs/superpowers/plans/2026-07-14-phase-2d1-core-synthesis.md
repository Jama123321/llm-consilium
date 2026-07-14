# Phase 2d-1 — Core Synthesis Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Anonymize council candidates with shuffled code-names, replace the judge prompt with a Fusion-style "reason, don't average, rewrite standalone" prompt, and surface a categorical `confidence` on every `CouncilResult` — no new modes, no extra model calls.

**Architecture:** A new pure `council/anonymize.py` produces a shuffled, code-named candidate block (reused later by peer-rank/debate). `aggregate()` feeds that block to a Fusion judge prompt, parses `DISAGREEMENTS:`/`CONFIDENCE:` from the reply, and returns a small `AggregateResult` dataclass (replacing the growing tuple). The vote path derives confidence from agreement. The orchestrator and MCP shape pass `confidence` through.

**Tech Stack:** Python 3.10, stdlib `random`/`re`, pytest, ruff.

## Global Constraints

- No new aggregation modes; only `vote`/`judge` change. No extra model calls.
- Borrowed designs (ai-council code-names, FreeLLMAPI Fusion prompt — both MIT) are
  **reimplemented** in our own wording/list with a one-line credit comment; no verbatim
  copy, no NOTICE file.
- Anonymization takes an injectable `random.Random` for hermetic tests.
- `confidence` ∈ {"high","medium","low",""} ("" = unknown). Categorical, not float.
- Python 3.10+; `ruff check .` clean + `pytest -q` green. Commits English imperative,
  no `Co-Authored-By`. Branch `phase-2d-council-quality`.

## File map

- `council/anonymize.py` — NEW: `CODE_NAMES`, `anonymize`.
- `council/types.py` — `AggregateResult`; `CouncilResult.confidence`.
- `council/aggregate.py` — Fusion prompt, anonymized candidates, confidence, `AggregateResult`.
- `council/orchestrator.py` — unpack `AggregateResult` at the aggregate call site.
- `consilium_mcp/server.py` — `_shape_council` adds `confidence`.
- `docs/usage-rule.md` — document `confidence`.
- Tests: `tests/test_anonymize.py` (new), `tests/test_aggregate.py`,
  `tests/test_orchestrator.py`, `tests/test_mcp_server.py`.

---

### Task 1: Anonymization primitive

**Files:**
- Create: `council/anonymize.py`
- Create: `tests/test_anonymize.py`

**Interfaces:**
- Produces: `CODE_NAMES: tuple[str, ...]` (12 names); `anonymize(answers: list[str], *, rng: random.Random | None = None) -> tuple[str, list[str]]` — shuffles answers with `rng or random.Random()`, labels each with a code-name (block order), returns `(labeled_block, codenames)` where `codenames[i]` labels block entry `i`. Raises `ValueError` if `len(answers) > len(CODE_NAMES)`.

- [ ] **Step 1: Write `tests/test_anonymize.py`**

```python
import random

import pytest

from council.anonymize import CODE_NAMES, anonymize


def test_anonymize_labels_and_shuffles_deterministically():
    answers = ["alpha", "bravo", "charlie"]
    block, names = anonymize(answers, rng=random.Random(0))
    # code-names are block-order prefix of CODE_NAMES
    assert names == list(CODE_NAMES[:3])
    # every code-name and every answer appears; format is "Name:\n<answer>"
    for name in names:
        assert f"{name}:" in block
    for a in answers:
        assert a in block
    # shuffle actually reorders for this seed (guards against identity mapping)
    order = [block.index(a) for a in answers]
    assert order != sorted(order)


def test_anonymize_hides_positional_index_and_aliases():
    block, _ = anonymize(["x", "y"], rng=random.Random(1))
    assert "[1]" not in block and "[2]" not in block


def test_anonymize_raises_when_too_many_answers():
    with pytest.raises(ValueError):
        anonymize([str(i) for i in range(len(CODE_NAMES) + 1)])


def test_anonymize_single_answer():
    block, names = anonymize(["solo"], rng=random.Random(0))
    assert names == [CODE_NAMES[0]] and "solo" in block
```

- [ ] **Step 2: Run — expect failure**

Run: `.venv/bin/pytest tests/test_anonymize.py -q`
Expected: FAIL (module `council.anonymize` missing).

- [ ] **Step 3: Implement `council/anonymize.py`**

```python
from __future__ import annotations

import random

# Code-name anonymization of council answers before synthesis/ranking so the judge
# weighs content, not model identity or list position. (Design idea: ai-council-mcp, MIT.)
CODE_NAMES: tuple[str, ...] = (
    "Aardvark", "Basilisk", "Cheetah", "Dingo", "Falcon", "Gecko",
    "Heron", "Ibis", "Jackal", "Kestrel", "Lynx", "Manta",
)


def anonymize(
    answers: list[str], *, rng: random.Random | None = None
) -> tuple[str, list[str]]:
    if len(answers) > len(CODE_NAMES):
        raise ValueError(
            f"too many answers to anonymize: {len(answers)} > {len(CODE_NAMES)}"
        )
    r = rng or random.Random()
    shuffled = list(answers)
    r.shuffle(shuffled)
    names = list(CODE_NAMES[: len(shuffled)])
    block = "\n\n".join(f"{name}:\n{ans}" for name, ans in zip(names, shuffled))
    return block, names
```

- [ ] **Step 4: Run — expect pass**

Run: `.venv/bin/ruff check council/anonymize.py tests/test_anonymize.py && .venv/bin/pytest tests/test_anonymize.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add council/anonymize.py tests/test_anonymize.py
git commit -m "feat(2d-1): code-name anonymization primitive for council synthesis"
```

---

### Task 2: Fusion judge + confidence + AggregateResult

**Files:**
- Modify: `council/types.py`
- Modify: `council/aggregate.py`
- Modify: `tests/test_aggregate.py`

**Interfaces:**
- Consumes: `anonymize` (Task 1).
- Produces: `AggregateResult(answer: str, mode: str, disagreements: str, judge_used: str | None, confidence: str)` (frozen). `CouncilResult` gains `confidence: str = ""`. `aggregate(prompt, answers, *, caller, judge_aliases, rng=None) -> AggregateResult`.

- [ ] **Step 1: Add `AggregateResult` and `CouncilResult.confidence` to `council/types.py`**

Add the dataclass (after `CouncilResult`) and the field:

```python
@dataclass(frozen=True)
class CouncilResult:
    answer: str
    per_member: list[MemberAnswer]
    disagreements: str
    judge_used: str | None
    mode: str
    note: str = ""
    confidence: str = ""


@dataclass(frozen=True)
class AggregateResult:
    answer: str
    mode: str
    disagreements: str
    judge_used: str | None
    confidence: str
```

- [ ] **Step 2: Rewrite the aggregate tests to the new shape (write the failing tests)**

Replace `tests/test_aggregate.py` unpacking. The aggregate now returns an
`AggregateResult`; update every test and add confidence coverage:

```python
import asyncio
import random

import pytest

from council import aggregate
from council.errors import AllMembersFailed, MemberCallError
from council.types import MemberAnswer


def _answers(*pairs):
    return [MemberAnswer(a, ok=ok, answer=ans, detail="ok" if ok else "x") for a, ok, ans in pairs]


async def _judge(alias, prompt):
    return "Merged best answer.\nDISAGREEMENTS: candidate differed on scope.\nCONFIDENCE: high"


def _run(ans, caller, judges=("chair",)):
    return asyncio.run(
        aggregate.aggregate("q", ans, caller=caller, judge_aliases=list(judges), rng=random.Random(0))
    )


def test_vote_on_closed_form_unanimous_is_high():
    r = _run(_answers(("m1", True, "Yes"), ("m2", True, "yes"), ("m3", True, "YES")), _judge)
    assert r.mode == "vote" and r.answer == "yes" and r.judge_used is None
    assert r.confidence == "high"


def test_vote_majority_is_medium():
    r = _run(_answers(("m1", True, "Yes"), ("m2", True, "yes"), ("m3", True, "No")), _judge)
    assert r.mode == "vote" and r.confidence == "medium"


def test_vote_plurality_is_low():
    r = _run(_answers(("m1", True, "A"), ("m2", True, "B"), ("m3", True, "C")), _judge)
    assert r.mode == "vote" and r.confidence == "low"


def test_judge_parses_answer_disagreements_and_confidence():
    ans = _answers(
        ("m1", True, "A long detailed explanation of the tradeoffs involved here."),
        ("m2", True, "Another multi sentence answer with different emphasis entirely."),
    )
    r = _run(ans, _judge)
    assert r.mode == "judge" and r.answer == "Merged best answer."
    assert "scope" in r.disagreements and "CONFIDENCE" not in r.disagreements
    assert r.judge_used == "chair" and r.confidence == "high"


def test_judge_prompt_uses_code_names_not_aliases_or_indices():
    captured = {}

    async def caller(alias, prompt):
        captured["prompt"] = prompt
        return "Merged.\nDISAGREEMENTS: none\nCONFIDENCE: medium"

    ans = _answers(
        ("council/cerebras-glm-4.7", True, "A long detailed answer about the tradeoffs here."),
        ("council/groq-gpt-oss-120b", True, "A different multi sentence answer entirely here."),
    )
    r = _run(ans, caller)
    assert r.confidence == "medium"
    assert "council/cerebras-glm-4.7" not in captured["prompt"]  # no model aliases
    assert "[1]" not in captured["prompt"] and "[2]" not in captured["prompt"]  # no indices
    from council.anonymize import CODE_NAMES
    assert any(f"{n}:" in captured["prompt"] for n in CODE_NAMES)  # code-names present


def test_judge_without_markers_yields_empty_disagreements_and_confidence():
    ans = _answers(
        ("m1", True, "A long detailed explanation of the tradeoffs involved here."),
        ("m2", True, "Another multi sentence answer with different emphasis entirely."),
    )

    async def caller(alias, prompt):
        return "Just a merged answer with several words here."

    r = _run(ans, caller)
    assert r.mode == "judge" and r.disagreements == "" and r.confidence == ""
    assert r.answer == "Just a merged answer with several words here."


def test_judge_falls_back_to_next_judge():
    ans = _answers(
        ("m1", True, "A long detailed explanation of the tradeoffs involved here."),
        ("m2", True, "Another multi sentence answer with different emphasis entirely."),
    )

    async def caller(alias, prompt):
        if alias == "chair":
            raise MemberCallError("chair", "429 rate-limited")
        return "Backup merge.\nDISAGREEMENTS: none\nCONFIDENCE: low"

    r = _run(ans, caller, judges=("chair", "backup"))
    assert r.mode == "judge" and r.judge_used == "backup" and r.answer == "Backup merge."
    assert r.confidence == "low"


def test_best_single_when_all_judges_fail():
    ans = _answers(
        ("m1", True, "short one"),
        ("m2", True, "A much longer and more substantive candidate answer here indeed."),
    )

    async def caller(alias, prompt):
        raise MemberCallError(alias, "429 rate-limited")

    r = _run(ans, caller, judges=("chair", "backup"))
    assert r.mode == "best-single" and r.judge_used is None and r.confidence == ""
    assert r.answer == "A much longer and more substantive candidate answer here indeed."


def test_all_failed_raises():
    ans = _answers(("m1", False, None), ("m2", False, None))
    with pytest.raises(AllMembersFailed):
        _run(ans, _judge)
```

- [ ] **Step 3: Run — expect failure**

Run: `.venv/bin/pytest tests/test_aggregate.py -q`
Expected: FAIL (aggregate returns a tuple / no `rng` param / no confidence).

- [ ] **Step 4: Rewrite `council/aggregate.py`**

```python
from __future__ import annotations

import random
import re
from collections import Counter

from council.anonymize import anonymize
from council.errors import AllMembersFailed, MemberCallError
from council.types import AggregateResult, AsyncCaller, MemberAnswer

# Fusion-style synthesis: reason and rewrite a standalone answer, don't average.
# (Design idea: FreeLLMAPI Fusion, MIT.) Candidates are code-name anonymized.
_JUDGE_PROMPT = (
    "You are the chair of a council. {n} members answered the question independently; "
    "their answers are labelled by code-name below. You do not know which member wrote "
    "which — weigh them equally.\n\n"
    "Synthesize the single best STANDALONE answer to the question. Reason about which "
    "claims are correct; do NOT average or split the difference, and NEVER refer to a "
    "member by code-name or number in your answer.\n\n"
    "After the answer, add two lines exactly:\n"
    "DISAGREEMENTS: <where members differed, or 'none'>\n"
    "CONFIDENCE: <high|medium|low>\n\n"
    "Question:\n{prompt}\n\nAnswers:\n{candidates}"
)

_CONF_RE = re.compile(r"(high|medium|low)", re.IGNORECASE)


def _looks_closed_form(answers: list[str]) -> bool:
    return all(len(a.strip().lower().rstrip(".!").split()) <= 3 for a in answers)


def _majority(answers: list[str]) -> str:
    norm = [a.strip().lower().rstrip(".!") for a in answers]
    return Counter(norm).most_common(1)[0][0]


def _vote_confidence(answers: list[str]) -> str:
    norm = [a.strip().lower().rstrip(".!") for a in answers]
    counts = Counter(norm)
    if len(counts) == 1:
        return "high"
    if counts.most_common(1)[0][1] * 2 > len(norm):
        return "medium"
    return "low"


def _split_marker(text: str, marker: str) -> tuple[str, str]:
    m = re.search(marker, text, re.IGNORECASE)
    if not m:
        return text, ""
    return text[: m.start()], text[m.end() :]


def _parse_judge(reply: str) -> tuple[str, str, str]:
    # Order in the prompt: answer, then DISAGREEMENTS line, then CONFIDENCE line.
    body, conf_tail = _split_marker(reply, r"CONFIDENCE:")
    answer, dis = _split_marker(body, r"DISAGREEMENTS:")
    conf_match = _CONF_RE.search(conf_tail)
    confidence = conf_match.group(1).lower() if conf_match else ""
    return answer.strip(), dis.strip(), confidence


async def aggregate(
    prompt: str,
    answers: list[MemberAnswer],
    *,
    caller: AsyncCaller,
    judge_aliases: list[str],
    rng: random.Random | None = None,
) -> AggregateResult:
    ok = [a.answer for a in answers if a.ok and a.answer is not None]
    if not ok:
        raise AllMembersFailed("every member abstained")
    if _looks_closed_form(ok):
        return AggregateResult(_majority(ok), "vote", "", None, _vote_confidence(ok))
    candidates, _ = anonymize(ok, rng=rng)
    for judge_alias in judge_aliases:
        try:
            reply = await caller(
                judge_alias,
                _JUDGE_PROMPT.format(n=len(ok), prompt=prompt, candidates=candidates),
            )
        except MemberCallError:
            continue
        answer, disagreements, confidence = _parse_judge(reply)
        return AggregateResult(answer, "judge", disagreements, judge_alias, confidence)
    return AggregateResult(max(ok, key=len), "best-single", "", None, "")
```

- [ ] **Step 5: Run — expect pass (aggregate suite)**

Run: `.venv/bin/ruff check council/ tests/test_aggregate.py && .venv/bin/pytest tests/test_aggregate.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add council/types.py council/aggregate.py tests/test_aggregate.py
git commit -m "feat(2d-1): Fusion judge prompt + confidence via AggregateResult"
```

---

### Task 3: Orchestrator passthrough of confidence

**Files:**
- Modify: `council/orchestrator.py`
- Modify: `tests/test_orchestrator.py`

**Interfaces:**
- Consumes: `AggregateResult` (Task 2).
- Produces: `Orchestrator.council` populates `CouncilResult.confidence` from the aggregate result.

- [ ] **Step 1: Add a failing confidence-passthrough test to `tests/test_orchestrator.py`**

```python
def test_council_passes_confidence_through():
    class ConfCaller:
        calls = []

        async def __call__(self, alias, prompt):
            self.calls.append((alias, prompt))
            if "Classify" in prompt:
                return "reasoning"
            if "DISAGREEMENTS" in prompt:  # the judge prompt
                return "Merged.\nDISAGREEMENTS: none\nCONFIDENCE: high"
            return "A detailed multi sentence answer explaining the tradeoffs."

    r = asyncio.run(_orch(ConfCaller()).council("explain the tradeoffs in depth please"))
    assert r.confidence == "high"
```

- [ ] **Step 2: Run — expect failure**

Run: `.venv/bin/pytest tests/test_orchestrator.py::test_council_passes_confidence_through -q`
Expected: FAIL (`CouncilResult.confidence` not populated / attribute unpack).

- [ ] **Step 3: Update the aggregate call site in `council/orchestrator.py`**

In `council`, replace the tuple unpack + `CouncilResult` construction:

```python
        result = await agg.aggregate(
            prompt, answers, caller=self._caller, judge_aliases=self._judge_order(chosen)
        )
        return CouncilResult(
            answer=result.answer, per_member=answers, disagreements=result.disagreements,
            judge_used=result.judge_used, mode=result.mode, note="; ".join(notes),
            confidence=result.confidence,
        )
```

- [ ] **Step 4: Run — expect pass (full orchestrator suite)**

Run: `.venv/bin/ruff check council/ tests/test_orchestrator.py && .venv/bin/pytest tests/test_orchestrator.py -q`
Expected: PASS (existing council tests still pass — the Recorder's judge reply lacks a CONFIDENCE line, so those `CouncilResult.confidence == ""`, which they don't assert).

- [ ] **Step 5: Commit**

```bash
git add council/orchestrator.py tests/test_orchestrator.py
git commit -m "feat(2d-1): thread synthesis confidence into CouncilResult"
```

---

### Task 4: MCP surface + usage rule

**Files:**
- Modify: `consilium_mcp/server.py`
- Modify: `tests/test_mcp_server.py`
- Modify: `docs/usage-rule.md`

**Interfaces:**
- Consumes: `CouncilResult.confidence` (Task 2).
- Produces: `_shape_council` includes `confidence`; usage rule documents it.

*(Depends only on Task 2's `CouncilResult.confidence`; disjoint files from Task 3 — may run in parallel with Task 3.)*

- [ ] **Step 1: Add a failing test to `tests/test_mcp_server.py`**

```python
def test_shape_council_includes_confidence():
    r = CouncilResult(
        answer="m", per_member=[], disagreements="none", judge_used="council/x",
        mode="judge", note="", confidence="high",
    )
    assert server._shape_council(r)["confidence"] == "high"
```

- [ ] **Step 2: Run — expect failure**

Run: `.venv/bin/pytest tests/test_mcp_server.py::test_shape_council_includes_confidence -q`
Expected: FAIL (`KeyError: 'confidence'`).

- [ ] **Step 3: Add `confidence` to `_shape_council` in `consilium_mcp/server.py`**

Add one line to the dict returned by `_shape_council`:

```python
        "confidence": r.confidence,
```

(place it alongside `"note": r.note` / the other scalar fields.)

- [ ] **Step 4: Document it in `docs/usage-rule.md`**

In the `council(...)` bullet's return description (inside the fenced ```markdown block),
note that the result now includes a `confidence` field. Append to the existing council
bullet:

```markdown
  The result includes `confidence` (high/medium/low) — the chair's confidence the
  synthesized answer is correct.
```

- [ ] **Step 5: Run — expect pass (full gate)**

Run: `.venv/bin/ruff check . && .venv/bin/pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add consilium_mcp/server.py tests/test_mcp_server.py docs/usage-rule.md
git commit -m "feat(2d-1): surface confidence in the MCP council output"
```

---

## Self-review

**Spec coverage:** anonymization primitive → T1; Fusion prompt + confidence + `AggregateResult` → T2; orchestrator passthrough → T3; MCP shape + usage rule → T4. Reimplemented (not copied) with credit comments → T1/T2. Injectable `rng` → T1/T2. No new modes, no extra calls → honored (vote derives locally; judge reuses the single call). All spec sections covered.

**Placeholder scan:** none — every step has complete code/commands.

**Type consistency:** `AggregateResult(answer, mode, disagreements, judge_used, confidence)` defined in T2, consumed in T2 (aggregate return) and T3 (orchestrator unpack via `.answer`/`.mode`/`.disagreements`/`.judge_used`/`.confidence`). `CouncilResult.confidence: str = ""` defined T2, populated T3, read T4. `anonymize(answers, *, rng) -> (block, codenames)` defined T1, consumed T2. `aggregate(..., rng=None) -> AggregateResult` consistent T2↔T3. `_shape_council` gains `confidence` T4.
