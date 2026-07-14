import random

import pytest

from council.anonymize import CODE_NAMES, anonymize


def test_anonymize_labels_and_shuffles_deterministically():
    answers = ["alpha", "bravo", "charlie"]
    block, names = anonymize(answers, rng=random.Random(0))
    # code-names are block-order prefix of CODE_NAMES
    assert names == list(CODE_NAMES[:3])
    # every code-name and every answer appears; format is "Name:\n<answer>"
    for name in names:
        assert f"{name}:" in block
    for a in answers:
        assert a in block
    # shuffle actually reorders for this seed (guards against identity mapping)
    order = [block.index(a) for a in answers]
    assert order != sorted(order)


def test_anonymize_hides_positional_index_and_aliases():
    block, _ = anonymize(["x", "y"], rng=random.Random(1))
    assert "[1]" not in block and "[2]" not in block


def test_anonymize_raises_when_too_many_answers():
    with pytest.raises(ValueError):
        anonymize([str(i) for i in range(len(CODE_NAMES) + 1)])


def test_anonymize_single_answer():
    block, names = anonymize(["solo"], rng=random.Random(0))
    assert names == [CODE_NAMES[0]] and "solo" in block
