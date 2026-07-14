from council import usage
from council.types import Member

CAPPED_REQ = Member("r", "A", ("general",), 3, 5, rpd=2, tpd=None)
CAPPED_TOK = Member("t", "A", ("general",), 3, 5, rpd=None, tpd=100)
UNCAPPED = Member("u", "A", ("general",), 3, 5)


def test_record_and_counts_roundtrip(tmp_path):
    store = usage.UsageStore(tmp_path / "u.db")
    store.record("r", 40, day="2026-07-14")
    store.record("r", 10, day="2026-07-14")
    assert store.counts("2026-07-14") == {"r": (2, 50)}


def test_available_drops_over_rpd_and_tpd():
    counts = {"r": (2, 0), "t": (1, 100)}  # r at rpd=2, t at tpd=100
    got = usage.available([CAPPED_REQ, CAPPED_TOK, UNCAPPED], counts)
    assert [m.alias for m in got] == ["u"]


def test_available_keeps_under_cap():
    counts = {"r": (1, 0), "t": (1, 50)}
    got = usage.available([CAPPED_REQ, CAPPED_TOK, UNCAPPED], counts)
    assert {m.alias for m in got} == {"r", "t", "u"}


def test_summary_shape_and_exhausted_flag():
    counts = {"r": (2, 0)}
    rows = {row["alias"]: row for row in usage.summary([CAPPED_REQ, UNCAPPED], counts)}
    assert rows["r"]["requests"] == 2 and rows["r"]["rpd"] == 2 and rows["r"]["exhausted"] is True
    assert rows["u"]["exhausted"] is False and rows["u"]["tokens"] == 0


def test_store_survives_unwritable_path():
    store = usage.UsageStore("/nonexistent-dir-xyz/u.db")
    store.record("r", 5)          # must not raise
    assert store.counts() == {}   # degrades to empty
