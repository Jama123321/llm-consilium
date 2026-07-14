from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

# (alias, prompt) -> answer text
AsyncCaller = Callable[[str, str], Awaitable[str]]


@dataclass(frozen=True)
class Member:
    alias: str
    privacy_tier: str
    capabilities: tuple[str, ...]
    strength: int
    rpm: int
    rpd: int | None = None
    tpd: int | None = None


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
