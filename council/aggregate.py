from __future__ import annotations

import random
import re
from collections import Counter

from council.anonymize import anonymize
from council.errors import AllMembersFailed, MemberCallError
from council.types import AggregateResult, AsyncCaller, MemberAnswer

# Fusion-style synthesis: reason and rewrite a standalone answer, don't average.
# (Design idea: FreeLLMAPI Fusion, MIT.) Candidates are code-name anonymized.
_JUDGE_PROMPT = (
    "You are the chair of a council. {n} members answered the question independently; "
    "their answers are labelled by code-name below. You do not know which member wrote "
    "which — weigh them equally.\n\n"
    "Synthesize the single best STANDALONE answer to the question. Reason about which "
    "claims are correct; do NOT average or split the difference, and NEVER refer to a "
    "member by code-name or number in your answer.\n\n"
    "After the answer, add two lines exactly:\n"
    "DISAGREEMENTS: <where members differed, or 'none'>\n"
    "CONFIDENCE: <high|medium|low>\n\n"
    "Question:\n{prompt}\n\nAnswers:\n{candidates}"
)

_CONF_RE = re.compile(r"(high|medium|low)", re.IGNORECASE)


def _looks_closed_form(answers: list[str]) -> bool:
    return all(len(a.strip().lower().rstrip(".!").split()) <= 3 for a in answers)


def _majority(answers: list[str]) -> str:
    norm = [a.strip().lower().rstrip(".!") for a in answers]
    return Counter(norm).most_common(1)[0][0]


def _vote_confidence(answers: list[str]) -> str:
    norm = [a.strip().lower().rstrip(".!") for a in answers]
    counts = Counter(norm)
    if len(counts) == 1:
        return "high"
    if counts.most_common(1)[0][1] * 2 > len(norm):
        return "medium"
    return "low"


def _split_marker(text: str, marker: str) -> tuple[str, str]:
    m = re.search(marker, text, re.IGNORECASE)
    if not m:
        return text, ""
    return text[: m.start()], text[m.end() :]


def _parse_judge(reply: str) -> tuple[str, str, str]:
    # Order in the prompt: answer, then DISAGREEMENTS line, then CONFIDENCE line.
    body, conf_tail = _split_marker(reply, r"CONFIDENCE:")
    answer, dis = _split_marker(body, r"DISAGREEMENTS:")
    conf_match = _CONF_RE.search(conf_tail)
    confidence = conf_match.group(1).lower() if conf_match else ""
    return answer.strip(), dis.strip(), confidence


async def aggregate(
    prompt: str,
    answers: list[MemberAnswer],
    *,
    caller: AsyncCaller,
    judge_aliases: list[str],
    rng: random.Random | None = None,
) -> AggregateResult:
    ok = [a.answer for a in answers if a.ok and a.answer is not None]
    if not ok:
        raise AllMembersFailed("every member abstained")
    if _looks_closed_form(ok):
        return AggregateResult(_majority(ok), "vote", "", None, _vote_confidence(ok))
    candidates, _ = anonymize(ok, rng=rng)
    for judge_alias in judge_aliases:
        try:
            reply = await caller(
                judge_alias,
                _JUDGE_PROMPT.format(n=len(ok), prompt=prompt, candidates=candidates),
            )
        except MemberCallError:
            continue
        answer, disagreements, confidence = _parse_judge(reply)
        return AggregateResult(answer, "judge", disagreements, judge_alias, confidence)
    return AggregateResult(max(ok, key=len), "best-single", "", None, "")
