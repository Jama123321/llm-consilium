import asyncio

import pytest

from council import aggregate
from council.errors import AllMembersFailed, MemberCallError
from council.types import MemberAnswer


def _answers(*pairs):
    return [MemberAnswer(a, ok=ok, answer=ans, detail="ok" if ok else "x") for a, ok, ans in pairs]


async def _judge(alias, prompt):
    return "Merged best answer.\nDISAGREEMENTS: candidate 2 differed on scope."


def test_vote_on_closed_form():
    ans = _answers(("m1", True, "Yes"), ("m2", True, "yes"), ("m3", True, "No"))
    out, mode, dis, judge = asyncio.run(
        aggregate.aggregate("q", ans, caller=_judge, judge_aliases=["chair"])
    )
    assert mode == "vote" and out == "yes" and dis == "" and judge is None


def test_judge_on_open_ended():
    ans = _answers(
        ("m1", True, "A long detailed explanation of the tradeoffs involved here."),
        ("m2", True, "Another multi sentence answer with different emphasis entirely."),
    )
    out, mode, dis, judge = asyncio.run(
        aggregate.aggregate("q", ans, caller=_judge, judge_aliases=["chair"])
    )
    assert mode == "judge" and out == "Merged best answer." and "scope" in dis and judge == "chair"


def test_judge_without_disagreements_marker():
    ans = _answers(
        ("m1", True, "A long detailed explanation of the tradeoffs involved here."),
        ("m2", True, "Another multi sentence answer with different emphasis entirely."),
    )

    async def caller(alias, prompt):
        return "Just a merged answer with several words here."

    out, mode, dis, judge = asyncio.run(
        aggregate.aggregate("q", ans, caller=caller, judge_aliases=["chair"])
    )
    assert mode == "judge" and dis == ""
    assert out == "Just a merged answer with several words here."


def test_judge_traverses_multiple_failures_in_order():
    ans = _answers(
        ("m1", True, "A long detailed explanation of the tradeoffs involved here."),
        ("m2", True, "Another multi sentence answer with different emphasis entirely."),
    )

    async def caller(alias, prompt):
        if alias in ("j1", "j2"):
            raise MemberCallError(alias, "429 rate-limited")
        return "Third judge merge.\nDISAGREEMENTS: candidates differed on emphasis."

    out, mode, dis, judge = asyncio.run(
        aggregate.aggregate("q", ans, caller=caller, judge_aliases=["j1", "j2", "j3"])
    )
    assert mode == "judge" and judge == "j3"


def test_judge_falls_back_to_next_judge():
    ans = _answers(
        ("m1", True, "A long detailed explanation of the tradeoffs involved here."),
        ("m2", True, "Another multi sentence answer with different emphasis entirely."),
    )

    async def caller(alias, prompt):
        if alias == "chair":
            raise MemberCallError("chair", "429 rate-limited")
        return "Backup merge.\nDISAGREEMENTS: none"

    out, mode, dis, judge = asyncio.run(
        aggregate.aggregate("q", ans, caller=caller, judge_aliases=["chair", "backup"])
    )
    assert mode == "judge" and judge == "backup" and out == "Backup merge."


def test_best_single_when_all_judges_fail():
    ans = _answers(
        ("m1", True, "short one"),
        ("m2", True, "A much longer and more substantive candidate answer here indeed."),
    )

    async def caller(alias, prompt):
        raise MemberCallError(alias, "429 rate-limited")

    out, mode, dis, judge = asyncio.run(
        aggregate.aggregate("q", ans, caller=caller, judge_aliases=["chair", "backup"])
    )
    assert mode == "best-single" and judge is None
    assert out == "A much longer and more substantive candidate answer here indeed."


def test_all_failed_raises():
    ans = _answers(("m1", False, None), ("m2", False, None))
    with pytest.raises(AllMembersFailed):
        asyncio.run(aggregate.aggregate("q", ans, caller=_judge, judge_aliases=["chair"]))
