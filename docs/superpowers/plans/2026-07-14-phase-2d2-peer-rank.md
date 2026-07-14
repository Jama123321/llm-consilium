# Phase 2d-2 — Peer-Rank Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `peer-rank` aggregation mode (members rank anonymized answers, mean-ordinal with self-vote exclusion, pick the winner verbatim), selectable via an explicit `mode` argument threaded aggregate → council → MCP; auto behaviour unchanged.

**Architecture:** Extend `anonymize.py` with `anonymize_pairs` (code-name↔owner mapping) and refactor `anonymize` to delegate. Refactor `aggregate()` to dispatch by `mode`: factor the current vote/judge paths into `_vote`/`_judge` helpers, add `_peer_rank` (parallel ranking fan-out + mean-ordinal, falls back to `_judge`). Thread `mode` through `Orchestrator.council` and the MCP `council` tool.

**Tech Stack:** Python 3.10, stdlib `random`/`re`/`asyncio`, pytest, ruff.

## Global Constraints

- Peer-rank returns the top-ranked member answer **verbatim** (no synthesis).
- **Self-vote exclusion mandatory:** a member's ranking never counts toward its own answer's score.
- Auto mode (`mode is None`) is byte-for-byte the current vote/judge behaviour.
- karpathy peer-rank is **reimplemented from the design** (no license) with self-vote exclusion added; credit comment names the idea.
- Determinism: `anonymize_pairs`/`anonymize` take an injectable `random.Random`; tests script ranker replies. No real model calls in tests.
- Graceful degradation: a ranker whose call fails or whose ranking is unparseable is dropped; `< 2` valid rankers → fall back to `_judge`.
- The repo's ruff enforces B905 — any `zip(...)` needs `strict=True`.
- Python 3.10+; `ruff check .` clean + `pytest -q` green. Commits English imperative, no `Co-Authored-By`. Branch `phase-2d2-peer-rank`.

## File map

- `council/anonymize.py` — `anonymize_pairs`; `anonymize` delegates.
- `council/aggregate.py` — `_vote`/`_judge`/`_peer_rank` helpers, `_RANK_PROMPT`, `_parse_ranking`, `mode` dispatch.
- `council/orchestrator.py` — `council` gains `mode`, passes it through.
- `consilium_mcp/server.py` — MCP `council` gains `mode` + docstring.
- `docs/usage-rule.md` — document `mode`.
- Tests: `tests/test_anonymize.py`, `tests/test_aggregate.py`, `tests/test_orchestrator.py`, `tests/test_mcp_server.py`.

---

### Task 1: `anonymize_pairs` + delegate

**Files:**
- Modify: `council/anonymize.py`
- Modify: `tests/test_anonymize.py`

**Interfaces:**
- Produces: `anonymize_pairs(pairs: list[tuple[str, str]], *, rng: random.Random | None = None) -> tuple[str, list[tuple[str, str]]]` — `pairs` are `(owner, text)`; returns `(labeled_block, mapping)` where `mapping[i] = (codename_i, owner_i)` in block order. Raises `ValueError` when `len(pairs) > len(CODE_NAMES)`. `anonymize(answers, *, rng)` unchanged in contract, now delegates to `anonymize_pairs`.

- [ ] **Step 1: Add failing tests to `tests/test_anonymize.py`**

```python
def test_anonymize_pairs_maps_codename_to_owner():
    import random as _random
    from council.anonymize import anonymize_pairs
    pairs = [("alice", "alpha"), ("bob", "bravo"), ("carol", "charlie")]
    block, mapping = anonymize_pairs(pairs, rng=_random.Random(0))
    # mapping is block-order (codename, owner); code-names are the prefix of CODE_NAMES
    assert [cn for cn, _ in mapping] == list(CODE_NAMES[:3])
    # every owner present exactly once; each owner's text sits under its code-name
    owners = {owner for _, owner in mapping}
    assert owners == {"alice", "bob", "carol"}
    text_of = {"alice": "alpha", "bob": "bravo", "carol": "charlie"}
    for codename, owner in mapping:
        assert f"{codename}:\n{text_of[owner]}" in block


def test_anonymize_delegates_and_keeps_contract():
    import random as _random
    block, names = anonymize(["x", "y"], rng=_random.Random(3))
    assert names == list(CODE_NAMES[:2])
    assert "x" in block and "y" in block and "[1]" not in block


def test_anonymize_pairs_raises_when_too_many():
    import pytest as _pytest
    from council.anonymize import anonymize_pairs
    with _pytest.raises(ValueError):
        anonymize_pairs([("o", str(i)) for i in range(len(CODE_NAMES) + 1)])
```

- [ ] **Step 2: Run — expect failure**

Run: `.venv/bin/pytest tests/test_anonymize.py -q`
Expected: FAIL (`anonymize_pairs` missing).

- [ ] **Step 3: Rewrite `council/anonymize.py`**

```python
from __future__ import annotations

import random

# Code-name anonymization of council answers before synthesis/ranking so the judge
# weighs content, not model identity or list position. (Design idea: ai-council-mcp, MIT.)
CODE_NAMES: tuple[str, ...] = (
    "Aardvark", "Basilisk", "Cheetah", "Dingo", "Falcon", "Gecko",
    "Heron", "Ibis", "Jackal", "Kestrel", "Lynx", "Manta",
)


def anonymize_pairs(
    pairs: list[tuple[str, str]], *, rng: random.Random | None = None
) -> tuple[str, list[tuple[str, str]]]:
    if len(pairs) > len(CODE_NAMES):
        raise ValueError(
            f"too many answers to anonymize: {len(pairs)} > {len(CODE_NAMES)}"
        )
    r = rng or random.Random()
    shuffled = list(pairs)
    r.shuffle(shuffled)
    names = list(CODE_NAMES[: len(shuffled)])
    block = "\n\n".join(
        f"{name}:\n{text}" for name, (_owner, text) in zip(names, shuffled, strict=True)
    )
    mapping = [
        (name, owner) for name, (owner, _text) in zip(names, shuffled, strict=True)
    ]
    return block, mapping


def anonymize(
    answers: list[str], *, rng: random.Random | None = None
) -> tuple[str, list[str]]:
    block, mapping = anonymize_pairs([("", a) for a in answers], rng=rng)
    return block, [codename for codename, _owner in mapping]
```

- [ ] **Step 4: Run — expect pass**

Run: `.venv/bin/ruff check council/anonymize.py tests/test_anonymize.py && .venv/bin/pytest tests/test_anonymize.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add council/anonymize.py tests/test_anonymize.py
git commit -m "feat(2d-2): anonymize_pairs with code-name to owner mapping"
```

---

### Task 2: Peer-rank + mode dispatch in `aggregate`

**Files:**
- Modify: `council/aggregate.py`
- Modify: `tests/test_aggregate.py`

**Interfaces:**
- Consumes: `anonymize_pairs` (Task 1).
- Produces: `aggregate(prompt, answers, *, caller, judge_aliases, rng=None, mode: str | None = None) -> AggregateResult` — `mode` ∈ {None (auto), "vote", "judge", "peer-rank"}; unknown → `ValueError`. Internal helpers `_vote(ok)`, `_judge(prompt, ok, *, caller, judge_aliases, rng)`, `_peer_rank(prompt, ok_members, *, caller, judge_aliases, rng)`.

- [ ] **Step 1: Add failing tests to `tests/test_aggregate.py`**

Append (keep the existing 2d-1 tests — they call `aggregate` without `mode`, still valid):

```python
def _members(*pairs):
    # pairs: (alias, answer)
    return [MemberAnswer(a, ok=True, answer=ans, detail="ok") for a, ans in pairs]


def test_peer_rank_picks_mean_ordinal_winner():
    ans = _members(
        ("m1", "Answer ONE is long and detailed and substantive."),
        ("m2", "Answer TWO is long and detailed and substantive."),
        ("m3", "Answer THREE is long and detailed and substantive."),
    )
    # With rng=Random(0), 3 answers get code-names Aardvark/Basilisk/Cheetah in some order.
    # Each ranker returns a fixed ranking; controller-independent because we assert on the
    # winning TEXT, resolved through the code-name mapping.
    async def caller(alias, prompt):
        # every ranker ranks the SAME code-name order (best->worst) as printed in `prompt`;
        # pick the first code-name that appears in the block as the unanimous winner
        import re as _re
        names = _re.findall(r"^([A-Z][a-z]+):$", prompt, _re.MULTILINE)
        return "RANKING: " + ", ".join(names)  # everyone agrees on block order

    r = asyncio.run(aggregate.aggregate(
        "q", ans, caller=caller, judge_aliases=["chair"], rng=random.Random(0), mode="peer-rank"))
    assert r.mode == "peer-rank"
    # unanimous first choice -> high confidence, and the winner is a real member answer
    assert r.confidence == "high"
    assert r.answer in [a.answer for a in ans]


def test_peer_rank_excludes_self_vote():
    ans = _members(
        ("m1", "Answer from m1, quite long and detailed here indeed."),
        ("m2", "Answer from m2, quite long and detailed here indeed."),
        ("m3", "Answer from m3, quite long and detailed here indeed."),
        ("m4", "Answer from m4, quite long and detailed here indeed."),
    )
    from council.anonymize import anonymize_pairs
    _, mapping = anonymize_pairs([(a.alias, a.answer) for a in ans], rng=random.Random(0))
    cn = {owner: c for c, owner in mapping}

    async def caller(alias, prompt):
        # m1 and m2 both rank m1 first; m3 and m4 both rank m2 first.
        # Counting self-votes, m1 and m2 tie (2 first-place each). Excluding m1's and m2's
        # self-votes, m2 wins outright (m3 & m4 back it, m1 does not) — so only correct
        # self-vote exclusion reliably picks m2.
        if alias in ("m1", "m2"):
            order = [cn["m1"], cn["m2"], cn["m3"], cn["m4"]]
        else:
            order = [cn["m2"], cn["m1"], cn["m3"], cn["m4"]]
        return "RANKING: " + ", ".join(order)

    r = asyncio.run(aggregate.aggregate(
        "q", ans, caller=caller, judge_aliases=["chair"], rng=random.Random(0), mode="peer-rank"))
    assert r.answer == "Answer from m2, quite long and detailed here indeed."


def test_peer_rank_falls_back_to_judge_when_too_few_rankers():
    ans = _members(("m1", "A long detailed answer about the tradeoffs here."),
                   ("m2", "Another long detailed answer with different emphasis."))

    async def caller(alias, prompt):
        if "RANKING" in prompt or "Rank them" in prompt:  # ranker prompt -> unparseable
            return "I cannot rank these."
        return "Judged merge.\nDISAGREEMENTS: none\nCONFIDENCE: medium"

    r = asyncio.run(aggregate.aggregate(
        "q", ans, caller=caller, judge_aliases=["chair"], rng=random.Random(0), mode="peer-rank"))
    assert r.mode == "judge" and r.answer == "Judged merge."


def test_mode_forces_path_and_unknown_raises():
    ans = _members(("m1", "yes"), ("m2", "yes"), ("m3", "no"))
    # closed-form, but mode='judge' forces the judge path
    async def judge(alias, prompt):
        return "Merged.\nDISAGREEMENTS: none\nCONFIDENCE: low"
    rj = asyncio.run(aggregate.aggregate(
        "q", ans, caller=judge, judge_aliases=["chair"], rng=random.Random(0), mode="judge"))
    assert rj.mode == "judge"
    # mode='vote' forces vote
    rv = asyncio.run(aggregate.aggregate(
        "q", ans, caller=judge, judge_aliases=["chair"], mode="vote"))
    assert rv.mode == "vote" and rv.answer == "yes"
    # unknown mode
    with pytest.raises(ValueError):
        asyncio.run(aggregate.aggregate("q", ans, caller=judge, judge_aliases=["chair"], mode="bogus"))
```

- [ ] **Step 2: Run — expect failure**

Run: `.venv/bin/pytest tests/test_aggregate.py -q`
Expected: FAIL (`aggregate` has no `mode`; no peer-rank).

- [ ] **Step 3: Rewrite `council/aggregate.py`**

Replace imports and add the peer-rank machinery + dispatch. Full file:

```python
from __future__ import annotations

import asyncio
import random
import re
from collections import Counter

from council.anonymize import anonymize, anonymize_pairs
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

# Peer-rank: each member ranks the anonymized answers; mean-ordinal with self-vote
# exclusion picks the winner verbatim. (Design idea: karpathy/llm-council; reimplemented,
# self-vote exclusion added.)
_RANK_PROMPT = (
    "Below are {n} anonymized candidate answers to a question, labelled by code-name. "
    "Rank them from best to worst by correctness and completeness; do not favour any "
    "particular one.\n\nEnd with exactly one line:\n"
    "RANKING: <Name>, <Name>, ... (list every code-name, best first)\n\n"
    "Question:\n{prompt}\n\nAnswers:\n{candidates}"
)

_CONF_RE = re.compile(r"(high|medium|low)", re.IGNORECASE)
_RANKING_RE = re.compile(r"RANKING:\s*(.+)", re.IGNORECASE)


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
    body, conf_tail = _split_marker(reply, r"CONFIDENCE:")
    answer, dis = _split_marker(body, r"DISAGREEMENTS:")
    conf_match = _CONF_RE.search(conf_tail)
    confidence = conf_match.group(1).lower() if conf_match else ""
    return answer.strip(), dis.strip(), confidence


def _parse_ranking(reply: str, valid: list[str]) -> list[str]:
    m = _RANKING_RE.search(reply)
    if not m:
        return []
    canon = {v.lower(): v for v in valid}
    order: list[str] = []
    for tok in re.split(r"[,\s]+", m.group(1).strip()):
        name = canon.get(tok.strip(" .").lower())
        if name is not None and name not in order:
            order.append(name)
    return order


def _vote(ok: list[str]) -> AggregateResult:
    return AggregateResult(_majority(ok), "vote", "", None, _vote_confidence(ok))


async def _judge(
    prompt: str, ok: list[str], *, caller: AsyncCaller, judge_aliases: list[str],
    rng: random.Random | None,
) -> AggregateResult:
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


async def _peer_rank(
    prompt: str, ok_members: list[MemberAnswer], *, caller: AsyncCaller,
    judge_aliases: list[str], rng: random.Random | None, timeout: float = 30.0,
) -> AggregateResult:
    pairs = [(a.alias, a.answer or "") for a in ok_members]
    block, mapping = anonymize_pairs(pairs, rng=rng)
    codenames = [cn for cn, _ in mapping]
    owner_of = dict(mapping)
    answer_of_alias = {a.alias: a.answer for a in ok_members}
    n = len(codenames)

    async def _rank(alias: str) -> tuple[str, list[str] | None]:
        try:
            reply = await asyncio.wait_for(
                caller(alias, _RANK_PROMPT.format(n=n, prompt=prompt, candidates=block)),
                timeout,
            )
        except Exception:  # noqa: BLE001 - a bad ranker is dropped, never crashes the vote
            return alias, None
        return alias, _parse_ranking(reply, codenames)

    results = await asyncio.gather(*[_rank(a.alias) for a in ok_members])
    rankings = {alias: order for alias, order in results if order}
    if len(rankings) < 2:
        ok = [a.answer for a in ok_members if a.answer is not None]
        return await _judge(prompt, ok, caller=caller, judge_aliases=judge_aliases, rng=rng)

    scores: dict[str, float] = {}
    first_votes: dict[str, tuple[int, int]] = {}  # codename -> (firsts, non-self voters)
    for cn in codenames:
        owner = owner_of[cn]
        ranks: list[int] = []
        firsts = 0
        for ranker, order in rankings.items():
            if ranker == owner:
                continue  # self-vote excluded
            ranks.append(order.index(cn) if cn in order else n)  # missing => tied last
            if order and order[0] == cn:
                firsts += 1
        scores[cn] = sum(ranks) / len(ranks) if ranks else float(n)
        first_votes[cn] = (firsts, len(ranks))

    winner = min(codenames, key=lambda cn: (scores[cn], -first_votes[cn][0], codenames.index(cn)))
    firsts, voters = first_votes[winner]
    unique_best = [scores[cn] for cn in codenames].count(scores[winner]) == 1
    if voters and firsts * 2 > voters:
        confidence = "high"
    elif unique_best and voters:
        confidence = "medium"
    else:
        confidence = "low"
    return AggregateResult(answer_of_alias[owner_of[winner]], "peer-rank", "", None, confidence)


async def aggregate(
    prompt: str,
    answers: list[MemberAnswer],
    *,
    caller: AsyncCaller,
    judge_aliases: list[str],
    rng: random.Random | None = None,
    mode: str | None = None,
) -> AggregateResult:
    ok_members = [a for a in answers if a.ok and a.answer is not None]
    ok = [a.answer for a in ok_members]
    if not ok:
        raise AllMembersFailed("every member abstained")
    if mode is None:
        if _looks_closed_form(ok):
            return _vote(ok)
        return await _judge(prompt, ok, caller=caller, judge_aliases=judge_aliases, rng=rng)
    if mode == "vote":
        return _vote(ok)
    if mode == "judge":
        return await _judge(prompt, ok, caller=caller, judge_aliases=judge_aliases, rng=rng)
    if mode == "peer-rank":
        return await _peer_rank(
            prompt, ok_members, caller=caller, judge_aliases=judge_aliases, rng=rng
        )
    raise ValueError(f"unknown aggregation mode: {mode}")
```

- [ ] **Step 4: Run — expect pass (aggregate suite)**

Run: `.venv/bin/ruff check council/ tests/test_aggregate.py && .venv/bin/pytest tests/test_aggregate.py -q`
Expected: PASS (existing 2d-1 tests + new peer-rank/mode tests).

- [ ] **Step 5: Commit**

```bash
git add council/aggregate.py tests/test_aggregate.py
git commit -m "feat(2d-2): peer-rank mode + mode dispatch in aggregate"
```

---

### Task 3: Orchestrator `mode` passthrough

**Files:**
- Modify: `council/orchestrator.py`
- Modify: `tests/test_orchestrator.py`

**Interfaces:**
- Consumes: `aggregate(..., mode=...)` (Task 2).
- Produces: `Orchestrator.council(prompt, *, members=None, size=None, mode: str | None = None, sensitivity="sensitive")` passes `mode` into `aggregate`.

*(Depends on Task 2's `mode` param. Disjoint files from Task 4 — may run in parallel with Task 4.)*

- [ ] **Step 1: Add a failing test to `tests/test_orchestrator.py`**

```python
def test_council_peer_rank_mode_reaches_aggregate():
    class RankCaller:
        calls = []

        async def __call__(self, alias, prompt):
            self.calls.append((alias, prompt))
            if "Classify" in prompt:
                return "reasoning"
            if "RANKING:" in prompt:  # the peer-rank ranker prompt
                return "RANKING: Aardvark, Basilisk, Cheetah"
            return "A detailed multi sentence answer explaining the tradeoffs."

    r = asyncio.run(_orch(RankCaller()).council("explain the tradeoffs", mode="peer-rank"))
    assert r.mode == "peer-rank"
```

- [ ] **Step 2: Run — expect failure**

Run: `.venv/bin/pytest tests/test_orchestrator.py::test_council_peer_rank_mode_reaches_aggregate -q`
Expected: FAIL (`council` has no `mode`).

- [ ] **Step 3: Add `mode` to `council` in `council/orchestrator.py`**

Change the signature and the aggregate call:

```python
    async def council(
        self, prompt: str, *, members: list[str] | None = None,
        size: int | None = None, mode: str | None = None, sensitivity: str = "sensitive",
    ) -> CouncilResult:
```

and pass `mode` into the aggregate call:

```python
        result = await agg.aggregate(
            prompt, answers, caller=self._caller,
            judge_aliases=self._judge_order(chosen), mode=mode,
        )
```

(Leave everything else in `council` unchanged.)

- [ ] **Step 4: Run — expect pass (full orchestrator suite)**

Run: `.venv/bin/ruff check council/ tests/test_orchestrator.py && .venv/bin/pytest tests/test_orchestrator.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add council/orchestrator.py tests/test_orchestrator.py
git commit -m "feat(2d-2): thread aggregation mode through Orchestrator.council"
```

---

### Task 4: MCP `mode` param + usage rule

**Files:**
- Modify: `consilium_mcp/server.py`
- Modify: `tests/test_mcp_server.py`
- Modify: `docs/usage-rule.md`

**Interfaces:**
- Consumes: `Orchestrator.council(mode=...)` (Task 3).
- Produces: MCP `council(prompt, sensitivity, members, size, mode)` passing `mode` through.

*(Test uses a FakeOrch capturing kwargs, so it is independent of Task 3's code; disjoint files — may run in parallel with Task 3.)*

- [ ] **Step 1: Add a failing test to `tests/test_mcp_server.py`**

```python
def test_council_tool_passes_mode(monkeypatch):
    captured = {}

    class FakeOrch:
        async def council(self, prompt, *, members=None, size=None, mode=None, sensitivity="sensitive"):
            captured.update(mode=mode, members=members, size=size, sensitivity=sensitivity)
            return CouncilResult("a", [], "none", None, "peer-rank", note="ok", confidence="high")

    monkeypatch.setattr(server, "_orch", FakeOrch())
    import asyncio
    out = asyncio.run(server.council("q", mode="peer-rank"))
    assert captured["mode"] == "peer-rank" and out["mode"] == "peer-rank"
```

- [ ] **Step 2: Run — expect failure**

Run: `.venv/bin/pytest tests/test_mcp_server.py::test_council_tool_passes_mode -q`
Expected: FAIL (`council` tool has no `mode`).

- [ ] **Step 3: Add `mode` to the MCP `council` tool in `consilium_mcp/server.py`**

Update the signature and passthrough (add `mode` param, document it, pass it through):

```python
@mcp.tool()
async def council(
    prompt: str, sensitivity: str = "sensitive",
    members: list[str] | None = None, size: int | None = None, mode: str | None = None,
) -> dict:
```

Add to the docstring (after the `size:` line):

```
    mode: aggregation strategy — omit for auto (majority vote for closed-form, else chair
        synthesis). "judge" forces chair synthesis; "vote" forces majority; "peer-rank"
        has members rank each other's anonymized answers and returns the winner verbatim
        (self-votes excluded).
```

And pass it through:

```python
    return _shape_council(
        await _get_orch().council(
            prompt, sensitivity=sensitivity, members=members, size=size, mode=mode,
        )
    )
```

- [ ] **Step 4: Document it in `docs/usage-rule.md`**

Append to the `council(...)` bullet inside the fenced ```markdown block:

```markdown
  Pass `mode="peer-rank"` to have members rank each other's anonymized answers (winner
  verbatim, self-votes excluded); `mode="judge"`/`"vote"` force those; omit for auto.
```

- [ ] **Step 5: Run — expect pass (full gate)**

Run: `.venv/bin/ruff check . && .venv/bin/pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add consilium_mcp/server.py tests/test_mcp_server.py docs/usage-rule.md
git commit -m "feat(2d-2): expose aggregation mode in the MCP council tool"
```

---

## Self-review

**Spec coverage:** `anonymize_pairs` + delegate → T1; `_peer_rank` (parallel ranking, self-vote exclusion, mean-ordinal, judge fallback) + `_parse_ranking` + `mode` dispatch (`vote`/`judge`/`peer-rank`/unknown→ValueError) → T2; orchestrator `mode` passthrough → T3; MCP `mode` + usage rule → T4. Reimplemented (credit comment), determinism (`rng`), degradation (<2 rankers → judge), self-vote exclusion → all in T2. Auto mode unchanged → T2 (`mode is None` branch identical to prior behaviour). All spec sections covered.

**Placeholder scan:** none — complete code/commands in every step.

**Type consistency:** `anonymize_pairs(pairs, *, rng) -> (block, list[(codename, owner)])` defined T1, consumed T2. `aggregate(..., mode=None) -> AggregateResult` consistent T2↔T3. `_vote`/`_judge`/`_peer_rank` signatures internal to T2. `Orchestrator.council(..., mode=None)` T3, called by MCP `council(mode=)` T4. `AggregateResult`/`CouncilResult` unchanged (mode already a field). All aligned.
