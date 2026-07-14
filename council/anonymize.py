from __future__ import annotations

import random

# Code-name anonymization of council answers before synthesis/ranking so the judge
# weighs content, not model identity or list position. (Design idea: ai-council-mcp, MIT.)
CODE_NAMES: tuple[str, ...] = (
    "Aardvark", "Basilisk", "Cheetah", "Dingo", "Falcon", "Gecko",
    "Heron", "Ibis", "Jackal", "Kestrel", "Lynx", "Manta",
)


def anonymize(
    answers: list[str], *, rng: random.Random | None = None
) -> tuple[str, list[str]]:
    if len(answers) > len(CODE_NAMES):
        raise ValueError(
            f"too many answers to anonymize: {len(answers)} > {len(CODE_NAMES)}"
        )
    r = rng or random.Random()
    shuffled = list(answers)
    r.shuffle(shuffled)
    names = list(CODE_NAMES[: len(shuffled)])
    block = "\n\n".join(
        f"{name}:\n{ans}" for name, ans in zip(names, shuffled, strict=True)
    )
    return block, names
