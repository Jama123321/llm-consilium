from __future__ import annotations

from collections import Counter

from council.errors import AllMembersFailed
from council.types import AsyncCaller, MemberAnswer

_JUDGE_PROMPT = (
    "You are the chair of a council. Below are {n} candidate answers to the same "
    "question. Produce the single best merged answer, then a final line starting with "
    "'DISAGREEMENTS:' noting where candidates differed (or 'none').\n\n"
    "Question:\n{prompt}\n\nCandidates:\n{candidates}"
)


def _looks_closed_form(answers: list[str]) -> bool:
    return all(len(a.strip().lower().rstrip(".!").split()) <= 3 for a in answers)


def _majority(answers: list[str]) -> str:
    norm = [a.strip().lower().rstrip(".!") for a in answers]
    return Counter(norm).most_common(1)[0][0]


async def aggregate(
    prompt: str, answers: list[MemberAnswer], *, caller: AsyncCaller, judge_alias: str
) -> tuple[str, str, str]:
    ok = [a.answer for a in answers if a.ok and a.answer is not None]
    if not ok:
        raise AllMembersFailed("every member abstained")
    if _looks_closed_form(ok):
        return _majority(ok), "vote", ""
    candidates = "\n".join(f"[{i + 1}] {a}" for i, a in enumerate(ok))
    merged = await caller(
        judge_alias, _JUDGE_PROMPT.format(n=len(ok), prompt=prompt, candidates=candidates)
    )
    disagreements = ""
    if "DISAGREEMENTS:" in merged:
        merged, _, disagreements = merged.partition("DISAGREEMENTS:")
    return merged.strip(), "judge", disagreements.strip()
