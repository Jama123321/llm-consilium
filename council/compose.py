from __future__ import annotations

from council.types import Member

_K_BY_CAPABILITY = {"fast": 3, "code": 4, "general": 4, "reasoning": 5}


def adaptive_k(capability: str) -> int:
    return _K_BY_CAPABILITY.get(capability, 4)


def _score(member: Member, capability: str) -> int:
    if not member.scores:
        return 0
    return member.scores.get(capability, max(member.scores.values()))


def compose_council(members: list[Member], *, k: int, capability: str) -> list[Member]:
    if not members or k <= 0:
        return []
    ranked = sorted(members, key=lambda m: (_score(m, capability), m.rpm), reverse=True)
    picked: list[Member] = []
    families: set[str] = set()
    for m in ranked:  # pass 1 — one per distinct provider family, strongest first
        if len(picked) >= k:
            break
        if m.provider_family not in families:
            picked.append(m)
            families.add(m.provider_family)
    for m in ranked:  # pass 2 — fill remaining slots by score
        if len(picked) >= k:
            break
        if m not in picked:
            picked.append(m)
    return picked[:k]
