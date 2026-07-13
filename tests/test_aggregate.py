import asyncio

import pytest

from council import aggregate
from council.errors import AllMembersFailed
from council.types import MemberAnswer


def _answers(*pairs):
    return [MemberAnswer(a, ok=ok, answer=ans, detail="ok" if ok else "x") for a, ok, ans in pairs]


async def _judge(alias, prompt):
    return "Merged best answer.\nDISAGREEMENTS: candidate 2 differed on scope."


def test_vote_on_closed_form():
    ans = _answers(("m1", True, "Yes"), ("m2", True, "yes"), ("m3", True, "No"))
    out, mode, dis = asyncio.run(
        aggregate.aggregate("q", ans, caller=_judge, judge_alias="chair")
    )
    assert mode == "vote" and out == "yes" and dis == ""


def test_judge_on_open_ended():
    ans = _answers(
        ("m1", True, "A long detailed explanation of the tradeoffs involved here."),
        ("m2", True, "Another multi sentence answer with different emphasis entirely."),
    )
    out, mode, dis = asyncio.run(
        aggregate.aggregate("q", ans, caller=_judge, judge_alias="chair")
    )
    assert mode == "judge" and out == "Merged best answer." and "scope" in dis


def test_all_failed_raises():
    ans = _answers(("m1", False, None), ("m2", False, None))
    with pytest.raises(AllMembersFailed):
        asyncio.run(aggregate.aggregate("q", ans, caller=_judge, judge_alias="chair"))
