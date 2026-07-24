from consilium_tg.store import BotStore


def test_active_session_lazily_created(tmp_path):
    s = BotStore(tmp_path / "tg.db")
    sid = s.active_session(100)
    assert sid > 0
    assert s.active_session(100) == sid           # stable
    assert s.list_sessions(100)[0]["active"] is True


def test_new_session_inherits_settings_and_switches(tmp_path):
    s = BotStore(tmp_path / "tg.db")
    a = s.active_session(100)
    s.set_setting(a, "tool", "ask")
    s.set_members(a, ["council/x", "council/y"])
    b = s.create_session(100)                      # /new
    assert b != a and s.active_session(100) == b
    assert s.get_settings(b)["tool"] == "ask"       # inherited
    assert s.get_settings(b)["members"] == ["council/x", "council/y"]
    assert s.switch_session(100, a) and s.active_session(100) == a


def test_settings_defaults_and_members_roundtrip(tmp_path):
    s = BotStore(tmp_path / "tg.db", default_sensitivity="sensitive")
    sid = s.active_session(1)
    d = s.get_settings(sid)
    assert d["tool"] == "council" and d["sensitivity"] == "sensitive"
    assert d["members"] == [] and d["show_footer"] is True and d["size"] is None
    s.set_members(sid, ["council/a"])
    assert s.get_settings(sid)["members"] == ["council/a"]


def test_messages_window_scoped_to_session(tmp_path):
    s = BotStore(tmp_path / "tg.db")
    a = s.active_session(1)
    b = s.create_session(1)
    s.add_message(a, "user", "in-a")
    s.add_message(b, "user", "in-b")
    assert [m["content"] for m in s.recent_messages(a, 8)] == ["in-a"]
    assert [m["content"] for m in s.recent_messages(b, 8)] == ["in-b"]


def test_autotitle_and_delete(tmp_path):
    s = BotStore(tmp_path / "tg.db")
    a = s.active_session(1)
    s.maybe_autotitle(a, "the first question here")
    assert "first question" in s.list_sessions(1)[0]["title"]
    b = s.create_session(1)
    s.delete_session(1, b)                          # active deleted -> newest remaining active
    assert s.active_session(1) == a


def test_degrades_on_bad_path(tmp_path):
    blocker = tmp_path / "f"
    blocker.write_text("x")
    s = BotStore(blocker / "nested" / "tg.db")      # parent is a file
    assert s.active_session(1) == -1                # sentinel, no raise
    assert s.list_sessions(1) == []
