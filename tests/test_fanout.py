import asyncio

from council import fanout
from council.errors import MemberCallError
from council.types import Member

M1 = Member("m1", "A", {"general": 3}, 5, "m1")
M2 = Member("m2", "A", {"general": 3}, 5, "m2")


def test_all_ok():
    async def caller(alias, prompt):
        return f"ans-{alias}"

    res = {a.alias: a for a in asyncio.run(fanout.fan_out("q", [M1, M2], caller))}
    assert res["m1"].ok and res["m1"].answer == "ans-m1"
    assert res["m2"].ok


def test_one_abstains_on_call_error():
    async def caller(alias, prompt):
        if alias == "m2":
            raise MemberCallError("m2", "429 rate-limited")
        return "ok"

    res = {a.alias: a for a in asyncio.run(fanout.fan_out("q", [M1, M2], caller))}
    assert res["m1"].ok
    assert not res["m2"].ok and res["m2"].answer is None and "429" in res["m2"].detail


def test_one_abstains_on_unexpected_error():
    async def caller(alias, prompt):
        if alias == "m2":
            raise ValueError("boom")
        return "ok"

    res = {a.alias: a for a in asyncio.run(fanout.fan_out("q", [M1, M2], caller))}
    assert res["m1"].ok
    assert res["m2"].ok is False and "error" in res["m2"].detail


def test_slow_member_times_out():
    async def caller(alias, prompt):
        if alias == "m2":
            await asyncio.sleep(1)
        return "ok"

    res = {a.alias: a for a in asyncio.run(fanout.fan_out("q", [M1, M2], caller, timeout=0.05))}
    assert res["m1"].ok
    assert not res["m2"].ok and res["m2"].detail == "timeout"
