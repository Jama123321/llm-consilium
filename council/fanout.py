from __future__ import annotations

import asyncio

from council.errors import MemberCallError
from council.types import AsyncCaller, Member, MemberAnswer


async def _call_one(
    member: Member, prompt: str, caller: AsyncCaller, sem: asyncio.Semaphore, timeout: float
) -> MemberAnswer:
    async with sem:
        try:
            answer = await asyncio.wait_for(caller(member.alias, prompt), timeout)
        except MemberCallError as exc:
            return MemberAnswer(member.alias, ok=False, answer=None, detail=exc.detail)
        except (asyncio.TimeoutError, TimeoutError):
            return MemberAnswer(member.alias, ok=False, answer=None, detail="timeout")
        return MemberAnswer(member.alias, ok=True, answer=answer, detail="ok")


async def fan_out(
    prompt: str, members: list[Member], caller: AsyncCaller, *, timeout: float = 30.0
) -> list[MemberAnswer]:
    # Per-member semaphore (sized to rpm) guards against saturating a member when the
    # same member is called concurrently; harmless at one-call-per-member.
    sems = {m.alias: asyncio.Semaphore(max(1, m.rpm)) for m in members}
    tasks = [
        asyncio.create_task(_call_one(m, prompt, caller, sems[m.alias], timeout)) for m in members
    ]
    return list(await asyncio.gather(*tasks))
