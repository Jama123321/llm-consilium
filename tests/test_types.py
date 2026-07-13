import dataclasses

import pytest

from council.errors import (
    AllMembersFailed,
    ConsiliumError,
    MemberCallError,
    NoEligibleMember,
    PrivacyRefusal,
)
from council.types import AskResult, CouncilResult, Member, MemberAnswer


def test_member_is_frozen():
    m = Member(alias="a", privacy_tier="A", capabilities=("general",), strength=3, rpm=5)
    with pytest.raises(dataclasses.FrozenInstanceError):
        m.strength = 4


def test_result_types_construct():
    ask = AskResult(answer="x", model_used="a", capability="code", note="n")
    council = CouncilResult(
        answer="x", per_member=[], disagreements="", judge_used=None, mode="vote"
    )
    ans = MemberAnswer(alias="a", ok=True, answer="x", detail="ok")
    assert ask.answer == "x" and council.mode == "vote" and ans.ok


def test_errors_subclass_base():
    for exc in (PrivacyRefusal, NoEligibleMember, AllMembersFailed, MemberCallError):
        assert issubclass(exc, ConsiliumError)


def test_member_call_error_carries_detail():
    e = MemberCallError("council/x", "429 rate-limited")
    assert e.alias == "council/x" and e.detail == "429 rate-limited"
