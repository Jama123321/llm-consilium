from __future__ import annotations

from council.errors import NoEligibleMember
from council.types import AsyncCaller, Member

CAPABILITIES = ("reasoning", "code", "fast", "general")

_CLASSIFY_PROMPT = (
    "Classify the task below into exactly one word from this list: "
    "reasoning, code, fast, general. Reply with only that word.\n\nTask:\n{prompt}"
)


def _normalize_capability(text: str) -> str:
    low = text.strip().lower()
    for cap in CAPABILITIES:
        if cap in low:
            return cap
    return "general"


async def classify(prompt: str, *, caller: AsyncCaller, classifier_alias: str) -> str:
    raw = await caller(classifier_alias, _CLASSIFY_PROMPT.format(prompt=prompt))
    return _normalize_capability(raw)


def select(members: list[Member], capability: str) -> Member:
    candidates = [m for m in members if capability in m.capabilities]
    if not candidates:
        raise NoEligibleMember(f"no member has capability '{capability}'")
    return max(candidates, key=lambda m: (m.strength, m.rpm))
