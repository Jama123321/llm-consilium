import asyncio

import pytest

from council import router
from council.errors import NoEligibleMember
from council.types import Member

STRONG = Member("strong", "A", ("reasoning", "general"), 5, 5)
FAST = Member("fast", "A", ("fast", "general"), 3, 30)
CODER = Member("coder", "A", ("code",), 4, 10)
MEMBERS = [STRONG, FAST, CODER]


def test_select_picks_highest_strength_with_capability():
    assert router.select(MEMBERS, "reasoning") is STRONG


def test_select_tie_breaks_on_rpm():
    a = Member("a", "A", ("general",), 3, 5)
    b = Member("b", "A", ("general",), 3, 30)
    assert router.select([a, b], "general") is b


def test_select_raises_when_no_capability():
    with pytest.raises(NoEligibleMember):
        router.select(MEMBERS, "vision")


def test_classify_normalizes_label():
    async def fake(alias, prompt):
        return "This is clearly a REASONING task."

    cap = asyncio.run(router.classify("solve x", caller=fake, classifier_alias="c"))
    assert cap == "reasoning"


def test_classify_defaults_to_general_on_unknown():
    async def fake(alias, prompt):
        return "banana"

    cap = asyncio.run(router.classify("hi", caller=fake, classifier_alias="c"))
    assert cap == "general"


def test_rank_orders_by_strength_then_rpm():
    assert [m.alias for m in router.rank(MEMBERS, "general")] == ["strong", "fast"]


def test_rank_raises_when_no_capability():
    with pytest.raises(NoEligibleMember):
        router.rank(MEMBERS, "vision")
