from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

# (alias, prompt) -> answer text
AsyncCaller = Callable[[str, str], Awaitable[str]]


@dataclass(frozen=True)
class Member:
    alias: str
    privacy_tier: str
    scores: dict[str, int]
    rpm: int
    provider_family: str = ""
    rpd: int | None = None
    tpd: int | None = None

    @property
    def capabilities(self) -> tuple[str, ...]:
        return tuple(self.scores)

    @property
    def strength(self) -> int:
        return max(self.scores.values()) if self.scores else 1


@dataclass(frozen=True)
class MemberAnswer:
    alias: str
    ok: bool
    answer: str | None
    detail: str


@dataclass(frozen=True)
class AskResult:
    answer: str
    model_used: str
    capability: str | None
    note: str


@dataclass(frozen=True)
class CouncilResult:
    answer: str
    per_member: list[MemberAnswer]
    disagreements: str
    judge_used: str | None
    mode: str
    note: str = ""
