# Phase 2d-3 — Debate Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `debate` aggregation mode — bounded (≤2) stance-steered CHALLENGE→REVISE rounds over the anonymized answers with Jaccard convergence early-exit, a Fusion synthesis of the final revised answers, and a convergence-derived `confidence` — selectable via `mode="debate"`.

**Architecture:** Pure convergence/revision helpers (`_jaccard`, `_mean_pairwise_jaccard`, `_parse_revision`) plus `_debate` land in `council/aggregate.py`, reusing `anonymize_pairs` and `_judge`. The `mode` dispatch gains a `"debate"` branch. `Orchestrator.council` needs no change (mode is already threaded generically); only the MCP docstring and usage rule mention `"debate"`.

**Tech Stack:** Python 3.10, stdlib `re`/`asyncio`/`random`, pytest, ruff.

## Global Constraints

- ≤2 CHALLENGE→REVISE rounds (`max_rounds=2`), early-exit when mean pairwise Jaccard of the revised answers ≥ 0.7; at least one full round runs before any exit.
- Debate returns a **Fusion synthesis** (`_judge`) of the final revised answers: `mode="debate"`, `judge_used` = the chair, `confidence` = rigor from final convergence (≥0.7 high / ≥0.4 medium / else low), overriding the judge's own confidence.
- Stance prompt carries the honesty guardrail verbatim: "Your stance is NOT a license to lie — flag only genuine errors, never invent them." Stances assigned round-robin `for`/`against`/`neutral`.
- Borrowed designs (PAL stance-steering Apache; DUH convergence/rigor AGPL) are **reimplemented** in our own wording/math with credit comments; no verbatim third-party code.
- Determinism: `anonymize_pairs` takes the injected `rng`; debate replies scripted in tests.
- Degradation: a member whose CHALLENGE call fails or lacks a parseable `REVISED:` keeps its prior answer; `< 2` usable answers → `_judge`.
- Auto mode and `vote`/`judge`/`peer-rank` unchanged. The repo's ruff enforces B905 (`strict=True`), B023 (no closures over loop vars — pass loop values as params), I001 (import order). Python 3.10+; `ruff check .` clean + `pytest -q` green. Commits English imperative, no `Co-Authored-By`. Branch `phase-2d3-debate`.

## File map

- `council/aggregate.py` — helpers, `_STANCES`/`_DEBATE_PROMPT`/`_debate`, `"debate"` dispatch.
- `consilium_mcp/server.py` — `council` docstring adds `"debate"`.
- `docs/usage-rule.md` — `mode` note adds `"debate"`.
- Tests: `tests/test_aggregate.py`, `tests/test_mcp_server.py`.

---

### Task 1: Convergence + revision helpers

**Files:**
- Modify: `council/aggregate.py`
- Modify: `tests/test_aggregate.py`

**Interfaces:**
- Produces: `_words(str)->list[str]`, `_jaccard(str,str)->float`, `_mean_pairwise_jaccard(list[str])->float`, `_parse_revision(str)->str|None`.

- [ ] **Step 1: Add failing tests to `tests/test_aggregate.py`** (append)

```python
def test_jaccard_identical_and_disjoint():
    assert aggregate._jaccard("the quick brown fox", "the quick brown fox") == 1.0
    assert aggregate._jaccard("alpha beta", "gamma delta") == 0.0


def test_jaccard_partial_and_empty():
    assert aggregate._jaccard("a b c", "b c d") == 0.5  # |∩|=2 |∪|=4
    assert aggregate._jaccard("", "") == 1.0
    assert aggregate._jaccard("x", "") == 0.0


def test_mean_pairwise_jaccard():
    assert aggregate._mean_pairwise_jaccard(["solo"]) == 1.0
    assert aggregate._mean_pairwise_jaccard(["a b", "a b", "a b"]) == 1.0
    assert aggregate._mean_pairwise_jaccard(["a", "b", "c"]) == 0.0


def test_parse_revision():
    assert aggregate._parse_revision("Critique.\nREVISED: my best answer now") == "my best answer now"
    assert aggregate._parse_revision("no marker here") is None
    assert aggregate._parse_revision("revised: lowercase marker works") == "lowercase marker works"
    assert aggregate._parse_revision("REVISED:    ") is None
```

- [ ] **Step 2: Run — expect failure**

Run: `.venv/bin/pytest tests/test_aggregate.py::test_jaccard_identical_and_disjoint -q`
Expected: FAIL (`_jaccard` missing).

- [ ] **Step 3: Add the helpers to `council/aggregate.py`** (after `_parse_ranking`)

```python
def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _jaccard(a: str, b: str) -> float:
    wa, wb = set(_words(a)), set(_words(b))
    if not wa and not wb:
        return 1.0
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def _mean_pairwise_jaccard(answers: list[str]) -> float:
    if len(answers) < 2:
        return 1.0
    pairs = [(i, j) for i in range(len(answers)) for j in range(i + 1, len(answers))]
    return sum(_jaccard(answers[i], answers[j]) for i, j in pairs) / len(pairs)


def _parse_revision(reply: str) -> str | None:
    m = re.search(r"REVISED:", reply, re.IGNORECASE)
    if not m:
        return None
    revised = reply[m.end() :].strip()
    return revised or None
```

- [ ] **Step 4: Run — expect pass**

Run: `.venv/bin/ruff check council/aggregate.py tests/test_aggregate.py && .venv/bin/pytest tests/test_aggregate.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add council/aggregate.py tests/test_aggregate.py
git commit -m "feat(2d-3): jaccard convergence + revision-parse helpers"
```

---

### Task 2: Debate loop + mode dispatch

**Files:**
- Modify: `council/aggregate.py`
- Modify: `tests/test_aggregate.py`

**Interfaces:**
- Consumes: Task 1 helpers, `anonymize_pairs`, `_judge`.
- Produces: `_debate(prompt, ok_members, *, caller, judge_aliases, rng, max_rounds=2, threshold=0.7, timeout=30.0) -> AggregateResult`; `aggregate(..., mode="debate")` dispatches to it.

- [ ] **Step 1: Add failing tests to `tests/test_aggregate.py`** (append)

```python
def test_debate_assigns_round_robin_stances():
    ans = _members(("m1", "alpha one"), ("m2", "bravo two"), ("m3", "charlie three"))
    stances = []

    async def caller(alias, prompt):
        if "debating" in prompt:
            for s in ("for", "against", "neutral"):
                if f"stance: {s}" in prompt:
                    stances.append(s)
            return "REVISED: converged shared answer text for all members here now"
        return "Merged.\nDISAGREEMENTS: none\nCONFIDENCE: high"

    asyncio.run(aggregate.aggregate(
        "q", ans, caller=caller, judge_aliases=["chair"], rng=random.Random(0), mode="debate"))
    assert set(stances) == {"for", "against", "neutral"}


def test_debate_converges_early_and_stops():
    ans = _members(("m1", "initial one"), ("m2", "initial two"), ("m3", "initial three"))
    calls = {"challenge": 0}

    async def caller(alias, prompt):
        if "debating" in prompt:
            calls["challenge"] += 1
            return "Critique.\nREVISED: consensus answer shared by all members here now"
        return "Merged consensus.\nDISAGREEMENTS: none\nCONFIDENCE: high"

    r = asyncio.run(aggregate.aggregate(
        "q", ans, caller=caller, judge_aliases=["chair"], rng=random.Random(0), mode="debate"))
    assert r.mode == "debate" and r.answer == "Merged consensus."
    assert calls["challenge"] == 3  # all identical -> converged after 1 round (not 2)
    assert r.confidence == "high"


def test_debate_runs_full_rounds_when_divergent():
    ans = _members(("m1", "alpha"), ("m2", "bravo"), ("m3", "charlie"))
    calls = {"challenge": 0}

    async def caller(alias, prompt):
        if "debating" in prompt:
            calls["challenge"] += 1
            return f"REVISED: wordone{calls['challenge']} wordtwo{calls['challenge']}"
        return "Merged.\nDISAGREEMENTS: they differ\nCONFIDENCE: medium"

    r = asyncio.run(aggregate.aggregate(
        "q", ans, caller=caller, judge_aliases=["chair"], rng=random.Random(0), mode="debate"))
    assert r.mode == "debate"
    assert calls["challenge"] == 6  # never converges -> 2 full rounds x 3 members
    assert r.confidence == "low"  # pairwise-disjoint revisions


def test_debate_single_member_falls_back_to_judge():
    ans = _members(("m1", "only answer here that is reasonably long indeed"))

    async def caller(alias, prompt):
        return "Judged.\nDISAGREEMENTS: none\nCONFIDENCE: high"

    r = asyncio.run(aggregate.aggregate(
        "q", ans, caller=caller, judge_aliases=["chair"], rng=random.Random(0), mode="debate"))
    assert r.mode == "judge"


def test_debate_failed_challenger_keeps_prior_answer():
    ans = _members(("m1", "prioralpha keeps"), ("m2", "priorbravo keeps"),
                   ("m3", "priorcharlie keeps"))
    captured = {}

    async def caller(alias, prompt):
        if "debating" in prompt:
            if alias == "m1":
                raise MemberCallError("m1", "boom")
            return "REVISED: revised shared text for the survivors here today"
        captured["judge"] = prompt
        return "Merged.\nDISAGREEMENTS: none\nCONFIDENCE: low"

    asyncio.run(aggregate.aggregate(
        "q", ans, caller=caller, judge_aliases=["chair"], rng=random.Random(0), mode="debate"))
    assert "prioralpha" in captured["judge"]  # m1's prior answer survived into synthesis
```

- [ ] **Step 2: Run — expect failure**

Run: `.venv/bin/pytest tests/test_aggregate.py::test_debate_converges_early_and_stops -q`
Expected: FAIL (no `debate` mode).

- [ ] **Step 3: Add debate to `council/aggregate.py`**

Add the stance constant + prompt near the other prompts:

```python
# Stance-steered debate: members critique the anonymized answers from an assigned stance,
# then revise; rounds repeat until word-set convergence. (Design ideas: PAL stance-steering
# Apache-2.0 + DUH debate/convergence AGPL — both reimplemented; the math is standard.)
_STANCES = ("for", "against", "neutral")
_DEBATE_PROMPT = (
    "You are a member of a council debating a question. Your assigned stance: {stance}.\n"
    "- for: argue in favour of the strongest position among the answers.\n"
    "- against: probe the answers for errors, gaps, and weak reasoning.\n"
    "- neutral: weigh the positions impartially.\n"
    "Your stance is NOT a license to lie — flag only genuine errors, never invent them.\n\n"
    "Below are the current anonymized candidate answers. Critique them from your stance, "
    "then give your OWN best revised answer to the question.\n\n"
    "End with exactly one line:\nREVISED: <your single best answer>\n\n"
    "Question:\n{prompt}\n\nCurrent answers:\n{candidates}"
)
```

Add `_debate` (after `_peer_rank`):

```python
async def _debate(
    prompt: str, ok_members: list[MemberAnswer], *, caller: AsyncCaller,
    judge_aliases: list[str], rng: random.Random | None,
    max_rounds: int = 2, threshold: float = 0.7, timeout: float = 30.0,
) -> AggregateResult:
    aliases = [a.alias for a in ok_members]
    current = {a.alias: (a.answer or "") for a in ok_members}
    if len(aliases) < 2:
        return await _judge(
            prompt, list(current.values()), caller=caller,
            judge_aliases=judge_aliases, rng=rng,
        )

    async def _challenge(index: int, alias: str, block: str) -> tuple[str, str | None]:
        stance = _STANCES[index % len(_STANCES)]
        try:
            reply = await asyncio.wait_for(
                caller(
                    alias,
                    _DEBATE_PROMPT.format(stance=stance, prompt=prompt, candidates=block),
                ),
                timeout,
            )
        except Exception:  # noqa: BLE001 - a failed debater keeps its prior answer
            return alias, None
        return alias, _parse_revision(reply)

    conv = 0.0
    for _round in range(max_rounds):
        block, _ = anonymize_pairs([(a, current[a]) for a in aliases], rng=rng)
        results = await asyncio.gather(
            *[_challenge(i, a, block) for i, a in enumerate(aliases)]
        )
        for alias, revised in results:
            if revised:
                current[alias] = revised
        conv = _mean_pairwise_jaccard(list(current.values()))
        if conv >= threshold:
            break

    confidence = "high" if conv >= 0.7 else "medium" if conv >= 0.4 else "low"
    judged = await _judge(
        prompt, list(current.values()), caller=caller,
        judge_aliases=judge_aliases, rng=rng,
    )
    return AggregateResult(
        judged.answer, "debate", judged.disagreements, judged.judge_used, confidence
    )
```

Add the dispatch branch in `aggregate` (before the final `raise ValueError`):

```python
    if mode == "debate":
        return await _debate(
            prompt, ok_members, caller=caller, judge_aliases=judge_aliases, rng=rng
        )
```

- [ ] **Step 4: Run — expect pass (aggregate suite)**

Run: `.venv/bin/ruff check council/ tests/test_aggregate.py && .venv/bin/pytest tests/test_aggregate.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add council/aggregate.py tests/test_aggregate.py
git commit -m "feat(2d-3): stance-steered debate mode with convergence early-exit"
```

---

### Task 3: MCP docstring + usage rule for `debate`

**Files:**
- Modify: `consilium_mcp/server.py`
- Modify: `tests/test_mcp_server.py`
- Modify: `docs/usage-rule.md`

**Interfaces:**
- No code contract change — `mode` already flows through the MCP `council` tool. This documents `"debate"` and asserts it reaches the orchestrator.

*(Independent of Tasks 1-2 — the MCP `mode` param already exists and the test uses a FakeOrch; may run in parallel with Task 2.)*

- [ ] **Step 1: Add a failing test to `tests/test_mcp_server.py`**

```python
def test_council_tool_passes_debate_mode(monkeypatch):
    captured = {}

    class FakeOrch:
        async def council(self, prompt, *, members=None, size=None, mode=None,
                          sensitivity="sensitive"):
            captured["mode"] = mode
            return CouncilResult("a", [], "none", "council/x", "debate", note="",
                                 confidence="high")

    monkeypatch.setattr(server, "_orch", FakeOrch())
    import asyncio
    out = asyncio.run(server.council("q", mode="debate"))
    assert captured["mode"] == "debate" and out["mode"] == "debate"
```

- [ ] **Step 2: Run — expect failure**

Run: `.venv/bin/pytest tests/test_mcp_server.py::test_council_tool_passes_debate_mode -q`
Expected: PASS already if the tool forwards `mode` (it does since 2d-2) — if so, this test just locks the behaviour; proceed to the docstring/doc updates. If it FAILS, the tool isn't forwarding `mode`; fix the passthrough.

- [ ] **Step 3: Add `"debate"` to the MCP `council` docstring in `consilium_mcp/server.py`**

In the `mode:` block of the `council` tool docstring (which already lists auto/"judge"/"vote"/"peer-rank"), append a sentence:

```
        "debate" runs a stance-steered debate — members critique and revise each other's
        anonymized answers under for/against/neutral stances until they converge, then the
        chair synthesizes; strongest for contentious questions, most free-tier calls.
```

- [ ] **Step 4: Document `"debate"` in `docs/usage-rule.md`**

Extend the `mode` note in the `council(...)` bullet (inside the fenced ```markdown block) to mention debate, e.g. append: `` `mode="debate"` runs a stance-steered debate that converges then synthesizes (most calls). ``

- [ ] **Step 5: Run — expect pass (full gate)**

Run: `.venv/bin/ruff check . && .venv/bin/pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add consilium_mcp/server.py tests/test_mcp_server.py docs/usage-rule.md
git commit -m "feat(2d-3): document debate mode in the MCP council tool"
```

---

## Self-review

**Spec coverage:** `_jaccard`/`_mean_pairwise_jaccard`/`_parse_revision`/`_words` → T1; `_debate` (stance round-robin, ≤2 rounds, convergence early-exit, degradation <2 & failed challenger, rigor confidence, Fusion synthesis) + `"debate"` dispatch → T2; MCP docstring + usage rule → T3. Honesty guardrail in `_DEBATE_PROMPT` → T2. Reimplemented with credit comment → T2. Determinism (`rng`) → T1/T2. All spec sections covered.

**Placeholder scan:** none — complete code/commands in every step.

**Type consistency:** `_debate(prompt, ok_members, *, caller, judge_aliases, rng, max_rounds=2, threshold=0.7, timeout=30.0) -> AggregateResult` defined and dispatched in T2. Helpers' signatures (T1) match their uses in `_debate` (T2). `mode="debate"` flows aggregate→council(unchanged)→MCP (T3). `AggregateResult`/`CouncilResult` unchanged. B023 avoided — `_challenge` takes `index`/`alias`/`block` as params, not loop closures.
