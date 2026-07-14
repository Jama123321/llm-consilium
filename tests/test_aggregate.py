import asyncio
import random

import pytest

from council import aggregate
from council.errors import AllMembersFailed, MemberCallError
from council.types import MemberAnswer


def _answers(*pairs):
    return [MemberAnswer(a, ok=ok, answer=ans, detail="ok" if ok else "x") for a, ok, ans in pairs]


async def _judge(alias, prompt):
    return "Merged best answer.\nDISAGREEMENTS: candidate differed on scope.\nCONFIDENCE: high"


def _run(ans, caller, judges=("chair",)):
    return asyncio.run(
        aggregate.aggregate(
            "q", ans, caller=caller, judge_aliases=list(judges), rng=random.Random(0)
        )
    )


def test_vote_on_closed_form_unanimous_is_high():
    r = _run(_answers(("m1", True, "Yes"), ("m2", True, "yes"), ("m3", True, "YES")), _judge)
    assert r.mode == "vote" and r.answer == "yes" and r.judge_used is None
    assert r.confidence == "high"


def test_vote_majority_is_medium():
    r = _run(_answers(("m1", True, "Yes"), ("m2", True, "yes"), ("m3", True, "No")), _judge)
    assert r.mode == "vote" and r.confidence == "medium"


def test_vote_plurality_is_low():
    r = _run(_answers(("m1", True, "A"), ("m2", True, "B"), ("m3", True, "C")), _judge)
    assert r.mode == "vote" and r.confidence == "low"


def test_judge_parses_answer_disagreements_and_confidence():
    ans = _answers(
        ("m1", True, "A long detailed explanation of the tradeoffs involved here."),
        ("m2", True, "Another multi sentence answer with different emphasis entirely."),
    )
    r = _run(ans, _judge)
    assert r.mode == "judge" and r.answer == "Merged best answer."
    assert "scope" in r.disagreements and "CONFIDENCE" not in r.disagreements
    assert r.judge_used == "chair" and r.confidence == "high"


def test_judge_prompt_uses_code_names_not_aliases_or_indices():
    captured = {}

    async def caller(alias, prompt):
        captured["prompt"] = prompt
        return "Merged.\nDISAGREEMENTS: none\nCONFIDENCE: medium"

    ans = _answers(
        ("council/cerebras-glm-4.7", True, "A long detailed answer about the tradeoffs here."),
        ("council/groq-gpt-oss-120b", True, "A different multi sentence answer entirely here."),
    )
    r = _run(ans, caller)
    assert r.confidence == "medium"
    assert "council/cerebras-glm-4.7" not in captured["prompt"]  # no model aliases
    assert "[1]" not in captured["prompt"] and "[2]" not in captured["prompt"]  # no indices
    from council.anonymize import CODE_NAMES
    assert any(f"{n}:" in captured["prompt"] for n in CODE_NAMES)  # code-names present


def test_judge_without_markers_yields_empty_disagreements_and_confidence():
    ans = _answers(
        ("m1", True, "A long detailed explanation of the tradeoffs involved here."),
        ("m2", True, "Another multi sentence answer with different emphasis entirely."),
    )

    async def caller(alias, prompt):
        return "Just a merged answer with several words here."

    r = _run(ans, caller)
    assert r.mode == "judge" and r.disagreements == "" and r.confidence == ""
    assert r.answer == "Just a merged answer with several words here."


def test_judge_falls_back_to_next_judge():
    ans = _answers(
        ("m1", True, "A long detailed explanation of the tradeoffs involved here."),
        ("m2", True, "Another multi sentence answer with different emphasis entirely."),
    )

    async def caller(alias, prompt):
        if alias == "chair":
            raise MemberCallError("chair", "429 rate-limited")
        return "Backup merge.\nDISAGREEMENTS: none\nCONFIDENCE: low"

    r = _run(ans, caller, judges=("chair", "backup"))
    assert r.mode == "judge" and r.judge_used == "backup" and r.answer == "Backup merge."
    assert r.confidence == "low"


def test_best_single_when_all_judges_fail():
    ans = _answers(
        ("m1", True, "short one"),
        ("m2", True, "A much longer and more substantive candidate answer here indeed."),
    )

    async def caller(alias, prompt):
        raise MemberCallError(alias, "429 rate-limited")

    r = _run(ans, caller, judges=("chair", "backup"))
    assert r.mode == "best-single" and r.judge_used is None and r.confidence == ""
    assert r.answer == "A much longer and more substantive candidate answer here indeed."


def test_all_failed_raises():
    ans = _answers(("m1", False, None), ("m2", False, None))
    with pytest.raises(AllMembersFailed):
        _run(ans, _judge)


def _members(*pairs):
    # pairs: (alias, answer)
    return [MemberAnswer(a, ok=True, answer=ans, detail="ok") for a, ans in pairs]


def test_peer_rank_picks_mean_ordinal_winner():
    ans = _members(
        ("m1", "Answer ONE is long and detailed and substantive."),
        ("m2", "Answer TWO is long and detailed and substantive."),
        ("m3", "Answer THREE is long and detailed and substantive."),
    )
    # With rng=Random(0), 3 answers get code-names Aardvark/Basilisk/Cheetah in some order.
    # Each ranker returns a fixed ranking; controller-independent because we assert on the
    # winning TEXT, resolved through the code-name mapping.
    async def caller(alias, prompt):
        # every ranker ranks the SAME code-name order (best->worst) as printed in `prompt`;
        # pick the first code-name that appears in the block as the unanimous winner
        import re as _re
        names = _re.findall(r"^([A-Z][a-z]+):$", prompt, _re.MULTILINE)
        return "RANKING: " + ", ".join(names)  # everyone agrees on block order

    r = asyncio.run(aggregate.aggregate(
        "q", ans, caller=caller, judge_aliases=["chair"], rng=random.Random(0), mode="peer-rank"))
    assert r.mode == "peer-rank"
    # unanimous first choice -> high confidence, and the winner is a real member answer
    assert r.confidence == "high"
    assert r.answer in [a.answer for a in ans]


def test_peer_rank_excludes_self_vote():
    ans = _members(
        ("m1", "Answer from m1, quite long and detailed here indeed."),
        ("m2", "Answer from m2, quite long and detailed here indeed."),
        ("m3", "Answer from m3, quite long and detailed here indeed."),
        ("m4", "Answer from m4, quite long and detailed here indeed."),
    )
    from council.anonymize import anonymize_pairs
    _, mapping = anonymize_pairs([(a.alias, a.answer) for a in ans], rng=random.Random(0))
    cn = {owner: c for c, owner in mapping}

    async def caller(alias, prompt):
        # m1 and m2 both rank m1 first; m3 and m4 both rank m2 first.
        # Counting self-votes, m1 and m2 tie (2 first-place each). Excluding m1's and m2's
        # self-votes, m2 wins outright (m3 & m4 back it, m1 does not) — so only correct
        # self-vote exclusion reliably picks m2.
        if alias in ("m1", "m2"):
            order = [cn["m1"], cn["m2"], cn["m3"], cn["m4"]]
        else:
            order = [cn["m2"], cn["m1"], cn["m3"], cn["m4"]]
        return "RANKING: " + ", ".join(order)

    r = asyncio.run(aggregate.aggregate(
        "q", ans, caller=caller, judge_aliases=["chair"], rng=random.Random(0), mode="peer-rank"))
    assert r.answer == "Answer from m2, quite long and detailed here indeed."


def test_peer_rank_falls_back_to_judge_when_too_few_rankers():
    ans = _members(("m1", "A long detailed answer about the tradeoffs here."),
                   ("m2", "Another long detailed answer with different emphasis."))

    async def caller(alias, prompt):
        if "RANKING" in prompt or "Rank them" in prompt:  # ranker prompt -> unparseable
            return "I cannot rank these."
        return "Judged merge.\nDISAGREEMENTS: none\nCONFIDENCE: medium"

    r = asyncio.run(aggregate.aggregate(
        "q", ans, caller=caller, judge_aliases=["chair"], rng=random.Random(0), mode="peer-rank"))
    assert r.mode == "judge" and r.answer == "Judged merge."


def test_mode_forces_path_and_unknown_raises():
    ans = _members(("m1", "yes"), ("m2", "yes"), ("m3", "no"))
    # closed-form, but mode='judge' forces the judge path
    async def judge(alias, prompt):
        return "Merged.\nDISAGREEMENTS: none\nCONFIDENCE: low"
    rj = asyncio.run(aggregate.aggregate(
        "q", ans, caller=judge, judge_aliases=["chair"], rng=random.Random(0), mode="judge"))
    assert rj.mode == "judge"
    # mode='vote' forces vote
    rv = asyncio.run(aggregate.aggregate(
        "q", ans, caller=judge, judge_aliases=["chair"], mode="vote"))
    assert rv.mode == "vote" and rv.answer == "yes"
    # unknown mode
    with pytest.raises(ValueError):
        asyncio.run(
            aggregate.aggregate("q", ans, caller=judge, judge_aliases=["chair"], mode="bogus"))


def test_parse_ranking_full_order():
    valid = ["Aardvark", "Basilisk", "Cheetah"]
    assert aggregate._parse_ranking("RANKING: Cheetah, Aardvark, Basilisk", valid) == [
        "Cheetah", "Aardvark", "Basilisk"]


def test_parse_ranking_partial_keeps_only_listed():
    valid = ["Aardvark", "Basilisk", "Cheetah"]
    # missing names are NOT appended by the parser (the scorer treats them as tied-last)
    assert aggregate._parse_ranking("RANKING: Basilisk, Aardvark", valid) == [
        "Basilisk", "Aardvark"]


def test_parse_ranking_absent_or_malformed_returns_empty():
    valid = ["Aardvark", "Basilisk"]
    assert aggregate._parse_ranking("I cannot rank these.", valid) == []
    assert aggregate._parse_ranking("", valid) == []


def test_parse_ranking_dedupes_and_drops_unknown():
    valid = ["Aardvark", "Basilisk"]
    # duplicate Aardvark collapses; unknown 'Zebra' dropped
    assert aggregate._parse_ranking(
        "RANKING: Aardvark, Aardvark, Zebra, Basilisk", valid) == ["Aardvark", "Basilisk"]


def test_parse_ranking_case_insensitive_marker_and_names():
    valid = ["Aardvark", "Basilisk"]
    assert aggregate._parse_ranking("ranking: basilisk, AARDVARK", valid) == [
        "Basilisk", "Aardvark"]
