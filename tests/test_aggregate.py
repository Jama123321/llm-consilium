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
        aggregate.aggregate(
            "q", ans, caller=caller, judge_aliases=list(judges), rng=random.Random(0)
        )
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
