from consilium_chat.store import ChatStore


def test_thread_and_message_roundtrip(tmp_path):
    s = ChatStore(tmp_path / "chat.db")
    tid = s.create_thread("First")
    s.add_message(tid, "user", "hi", None)
    s.add_message(tid, "assistant", "hello", {"mode": "vote", "confidence": "high"})
    msgs = s.get_messages(tid)
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[1]["meta"]["mode"] == "vote"
    assert s.list_threads()[0]["id"] == tid


def test_rename_and_delete(tmp_path):
    s = ChatStore(tmp_path / "chat.db")
    tid = s.create_thread("x")
    s.rename_thread(tid, "renamed")
    assert s.list_threads()[0]["title"] == "renamed"
    s.delete_thread(tid)
    assert s.list_threads() == []


def test_degrades_on_bad_path(tmp_path):
    blocker = tmp_path / "f"
    blocker.write_text("x")
    s = ChatStore(blocker / "nested" / "chat.db")  # parent is a file -> NotADirectoryError
    assert s.create_thread("x") == -1   # sentinel, no raise
    assert s.list_threads() == []
