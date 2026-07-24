from consilium_tg.access import AccessStore


def test_owner_always_allowed(tmp_path):
    a = AccessStore(tmp_path / "acc.json", owner_id=7)
    assert a.is_owner(7) and a.is_allowed(7)
    assert not a.is_allowed(9)


def test_pairing_flow(tmp_path):
    a = AccessStore(tmp_path / "acc.json", owner_id=7)
    a.request_access(9, "nine")
    assert a.list_pending() == {"9": "nine"}
    assert a.approve(9) and a.is_allowed(9)
    assert a.list_pending() == {}


def test_deny_removes_pending(tmp_path):
    a = AccessStore(tmp_path / "acc.json", owner_id=7)
    a.request_access(9, "nine")
    assert a.deny(9) and not a.is_allowed(9) and a.list_pending() == {}


def test_degrades_on_bad_path(tmp_path):
    blocker = tmp_path / "f"
    blocker.write_text("x")
    a = AccessStore(blocker / "nested" / "acc.json", owner_id=7)  # parent is a file
    a.request_access(9, "nine")          # no raise
    assert a.is_allowed(7)               # owner still allowed (in-memory)
    assert a.list_pending() == {}        # unreadable -> empty, no raise
