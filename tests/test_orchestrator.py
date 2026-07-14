import asyncio

import pytest

from council.errors import AllMembersFailed, MemberCallError, PrivacyRefusal
from council.orchestrator import Orchestrator
from council.types import Member

GLM = Member(
    "council/cerebras-glm-4.7", "A", {"reasoning": 5, "general": 5, "code": 5}, 5, "cerebras"
)
GROQ = Member(
    "council/groq-gpt-oss-120b",
    "A",
    {"reasoning": 4, "code": 4, "general": 4, "fast": 4},
    30,
    "groq",
)
CF = Member("council/cloudflare-llama-70b", "A", {"general": 3, "fast": 3}, 10, "cloudflare")
TIERB = Member("council/some-b", "B", {"general": 2}, 10, "someb")
ALL = [GLM, GROQ, CF, TIERB]


class Recorder:
    def __init__(self, answer="A detailed multi sentence answer explaining the tradeoffs."):
        self.answer = answer
        self.calls = []

    async def __call__(self, alias, prompt):
        self.calls.append((alias, prompt))
        if "DISAGREEMENTS" in prompt:
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


def test_council_auto_composes_vendor_diverse():
    rec = Recorder()
    r = asyncio.run(_orch(rec).council("explain the tradeoffs in depth please"))
    # sensitive -> only Tier-A (GLM/GROQ/CF); TIERB excluded
    assert {a.alias for a in r.per_member} == {
        "council/cerebras-glm-4.7", "council/groq-gpt-oss-120b", "council/cloudflare-llama-70b",
    }
    assert r.mode == "judge" and r.judge_used == "council/cerebras-glm-4.7"


def test_council_passes_confidence_through():
    class ConfCaller:
        calls = []

        async def __call__(self, alias, prompt):
            self.calls.append((alias, prompt))
            if "Classify" in prompt:
                return "reasoning"
            if "DISAGREEMENTS" in prompt:  # the judge prompt
                return "Merged.\nDISAGREEMENTS: none\nCONFIDENCE: high"
            return "A detailed multi sentence answer explaining the tradeoffs."

    r = asyncio.run(_orch(ConfCaller()).council("explain the tradeoffs in depth please"))
    assert r.confidence == "high"


def test_council_peer_rank_mode_reaches_aggregate():
    class RankCaller:
        calls = []

        async def __call__(self, alias, prompt):
            self.calls.append((alias, prompt))
            if "Classify" in prompt:
                return "reasoning"
            if "RANKING:" in prompt:  # the peer-rank ranker prompt
                return "RANKING: Aardvark, Basilisk, Cheetah"
            return "A detailed multi sentence answer explaining the tradeoffs."

    r = asyncio.run(_orch(RankCaller()).council("explain the tradeoffs", mode="peer-rank"))
    assert r.mode == "peer-rank"


def test_council_manual_roster_used():
    rec = Recorder()
    r = asyncio.run(_orch(rec).council("x", members=["council/groq-gpt-oss-120b"]))
    assert [a.alias for a in r.per_member] == ["council/groq-gpt-oss-120b"]


def test_council_manual_tier_b_dropped_on_sensitive():
    rec = Recorder()
    r = asyncio.run(_orch(rec).council(
        "x", members=["council/groq-gpt-oss-120b", "council/some-b"], sensitivity="sensitive"))
    aliases = {a.alias for a in r.per_member}
    assert "council/some-b" not in aliases
    assert "council/groq-gpt-oss-120b" in aliases
    assert "some-b" in r.note and "drop" in r.note.lower()
    assert all("council/some-b" != alias for alias, _ in rec.calls)  # never called


def test_council_manual_tier_b_allowed_on_public():
    rec = Recorder()
    r = asyncio.run(_orch(rec).council("x", members=["council/some-b"], sensitivity="public"))
    assert [a.alias for a in r.per_member] == ["council/some-b"]


def test_council_size_override():
    rec = Recorder()
    r = asyncio.run(_orch(rec).council("deep reasoning task", size=2))
    assert len(r.per_member) == 2


def test_council_unknown_alias_dropped_falls_back_to_auto():
    rec = Recorder()
    r = asyncio.run(_orch(rec).council("x", members=["council/nope"]))
    assert len(r.per_member) >= 1  # empty roster -> auto-composed
    assert "nope" in r.note


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


def test_classifier_never_a_tier_filtered_member():
    tierb_classifier = Member("council/tierb-classifier", "B", {"general": 2}, 99, "tierbc")
    o = Orchestrator([GLM, GROQ, CF, tierb_classifier], Recorder(),
                     classifier_alias="council/tierb-classifier")
    asyncio.run(o.ask("a reasoning task"))
    classify_calls = [alias for alias, prompt in o._caller.calls if "Classify" in prompt]
    assert classify_calls
    assert all(a != "council/tierb-classifier" for a in classify_calls)


def test_judge_order_excludes_chair_not_in_chosen():
    order = _orch(Recorder())._judge_order([GROQ, CF])
    assert "council/cerebras-glm-4.7" not in order
    assert order[0] == "council/groq-gpt-oss-120b"


def test_judge_order_puts_chair_first_when_present():
    order = _orch(Recorder())._judge_order([GROQ, CF, GLM])
    assert order[0] == "council/cerebras-glm-4.7"


class _FakeStore:
    def __init__(self, counts):
        self._counts = counts

    def counts(self, day=None):
        return self._counts


def test_council_skips_exhausted_member():
    # GLM exhausted by tpd; council should fall back to the remaining trio members
    store = _FakeStore({"council/cerebras-glm-4.7": (0, 10**9)})
    members = [
        Member("council/cerebras-glm-4.7", "A", {"reasoning": 5}, 5, "cerebras", tpd=1000000),
        GROQ, CF,
    ]
    o = Orchestrator(members, Recorder(), store=store)
    r = asyncio.run(o.council("explain the tradeoffs in depth please"))
    assert "council/cerebras-glm-4.7" not in {a.alias for a in r.per_member}


def test_council_falls_back_when_all_exhausted():
    store = _FakeStore({m.alias: (0, 10**9) for m in [GLM, GROQ, CF]})
    members = [
        Member(GLM.alias, "A", GLM.scores, 5, "cerebras", tpd=1),
        Member(GROQ.alias, "A", GROQ.scores, 30, "groq", tpd=1),
        Member(CF.alias, "A", CF.scores, 10, "cloudflare", tpd=1),
    ]
    o = Orchestrator(members, Recorder(), store=store)
    r = asyncio.run(o.council("explain the tradeoffs in depth please"))
    assert len(r.per_member) == 3  # fell back to the full gated trio


def test_usage_summary_returns_rows():
    o = Orchestrator(ALL, Recorder(), store=_FakeStore({"council/cerebras-glm-4.7": (3, 500)}))
    rows = {row["alias"]: row for row in o.usage_summary()}
    assert rows["council/cerebras-glm-4.7"]["requests"] == 3
