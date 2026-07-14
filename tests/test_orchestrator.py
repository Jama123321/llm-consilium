import asyncio

import pytest

from council.errors import AllMembersFailed, MemberCallError, PrivacyRefusal
from council.orchestrator import Orchestrator
from council.types import Member

GLM = Member("council/cerebras-glm-4.7", "A", ("reasoning", "general", "code"), 5, 5)
GROQ = Member("council/groq-gpt-oss-120b", "A", ("reasoning", "code", "general", "fast"), 4, 30)
CF = Member("council/cloudflare-llama-70b", "A", ("general", "fast"), 3, 10)
TIERB = Member("council/some-b", "B", ("general",), 2, 10)
ALL = [GLM, GROQ, CF, TIERB]


class Recorder:
    def __init__(self, answer="A detailed multi sentence answer explaining the tradeoffs."):
        self.answer = answer
        self.calls = []

    async def __call__(self, alias, prompt):
        self.calls.append((alias, prompt))
        if "DISAGREEMENTS" in prompt or "chair" in alias:
            return "Merged.\nDISAGREEMENTS: none"
        if "Classify" in prompt:
            return "reasoning"
        return self.answer


def _orch(caller):
    return Orchestrator(ALL, caller)


def test_ask_direct_model_skips_classify():
    rec = Recorder()
    r = asyncio.run(_orch(rec).ask("hi", model="council/groq-gpt-oss-120b"))
    assert r.model_used == "council/groq-gpt-oss-120b" and r.note == "direct"
    assert all("Classify" not in p for _, p in rec.calls)


def test_ask_auto_classifies_then_selects_strongest():
    rec = Recorder()
    r = asyncio.run(_orch(rec).ask("prove a theorem"))
    # classify -> "reasoning" -> strongest reasoning member is GLM (strength 5)
    assert r.capability == "reasoning" and r.model_used == "council/cerebras-glm-4.7"


def test_ask_sensitive_refuses_tier_b_model():
    with pytest.raises(PrivacyRefusal):
        asyncio.run(_orch(Recorder()).ask("hi", model="council/some-b", sensitivity="sensitive"))


def test_council_default_trio_and_judge():
    rec = Recorder()
    r = asyncio.run(_orch(rec).council("explain the tradeoffs in depth please"))
    assert {a.alias for a in r.per_member} == {
        "council/cerebras-glm-4.7",
        "council/groq-gpt-oss-120b",
        "council/cloudflare-llama-70b",
    }
    assert r.mode == "judge" and r.judge_used == "council/cerebras-glm-4.7"


def test_ask_auto_falls_back_on_rate_limit():
    class FB:
        async def __call__(self, alias, prompt):
            if "Classify" in prompt:
                return "reasoning"
            if alias == "council/cerebras-glm-4.7":
                raise MemberCallError(alias, "429 rate-limited")
            return "fallback answer"

    r = asyncio.run(_orch(FB()).ask("prove a theorem"))
    assert r.model_used == "council/groq-gpt-oss-120b"
    assert "429" in r.note


def test_ask_raises_all_members_failed_when_all_rate_limited():
    class AllFail:
        async def __call__(self, alias, prompt):
            if "Classify" in prompt:
                return "reasoning"
            raise MemberCallError(alias, "429 rate-limited")

    with pytest.raises(AllMembersFailed):
        asyncio.run(_orch(AllFail()).ask("x"))
