from __future__ import annotations

import random

# Code-name anonymization of council answers before synthesis/ranking so the judge
# weighs content, not model identity or list position. (Design idea: ai-council-mcp, MIT.)
CODE_NAMES: tuple[str, ...] = (
    "Aardvark", "Basilisk", "Cheetah", "Dingo", "Falcon", "Gecko",
    "Heron", "Ibis", "Jackal", "Kestrel", "Lynx", "Manta",
)


def anonymize_pairs(
    pairs: list[tuple[str, str]], *, rng: random.Random | None = None
) -> tuple[str, list[tuple[str, str]]]:
    if len(pairs) > len(CODE_NAMES):
        raise ValueError(
            f"too many answers to anonymize: {len(pairs)} > {len(CODE_NAMES)}"
        )
    r = rng or random.Random()
    shuffled = list(pairs)
    r.shuffle(shuffled)
    names = list(CODE_NAMES[: len(shuffled)])
    block = "\n\n".join(
        f"{name}:\n{text}" for name, (_owner, text) in zip(names, shuffled, strict=True)
    )
    mapping = [
        (name, owner) for name, (owner, _text) in zip(names, shuffled, strict=True)
    ]
    return block, mapping


def anonymize(
    answers: list[str], *, rng: random.Random | None = None
) -> tuple[str, list[str]]:
    block, mapping = anonymize_pairs([("", a) for a in answers], rng=rng)
    return block, [codename for codename, _owner in mapping]
