from consilium_tg import render


def test_progress_marks():
    t = render.progress_text(["council/a", "council/b"], {"council/a": True}, aggregating=False)
    assert "✓ a" in t and "○ b" in t


def test_progress_aggregating():
    t = render.progress_text(["council/a"], {"council/a": True}, aggregating=True)
    assert "✓ a" in t and "synth" in t.lower()


def test_answer_footer_on_off():
    meta = {"mode": "judge", "confidence": "high", "model": "council/x"}
    assert render.answer_text("hi", meta, show_footer=False) == "hi"
    out = render.answer_text("hi", meta, show_footer=True)
    assert "hi" in out and "judge" in out and "high" in out


def test_answer_surfaces_note():
    meta = {"mode": "judge", "note": "dropped X"}
    out = render.answer_text("hi", meta, show_footer=True)
    assert "hi" in out and "judge" in out and "dropped X" in out
    assert render.answer_text("hi", meta, show_footer=False) == "hi"


def test_chunk_splits_4096():
    parts = render.chunk("x" * 9000)
    assert len(parts) == 3 and all(len(p) <= 4096 for p in parts)
    assert render.chunk("") == [""]


def test_models_layout_marks_selected():
    rows = render.models_layout(
        [{"alias": "council/a", "tier": "A"}, {"alias": "council/b", "tier": "B"}],
        selected=["council/a"],
    )
    flat = [c for row in rows for (label, c) in row]
    labels = [label for row in rows for (label, c) in row]
    assert "mdl:auto" in flat and "mdl:council/a" in flat
    assert any("☑" in x and " a " in f" {x} " for x in labels)   # a selected
    assert any("☐" in x for x in labels)                          # b not


def test_sessions_layout_marks_active():
    rows = render.sessions_layout([
        {"id": 5, "title": "work", "active": True},
        {"id": 4, "title": "home", "active": False},
    ])
    labels = [label for row in rows for (label, c) in row]
    cbs = [c for row in rows for (label, c) in row]
    assert any("●" in x for x in labels) and "sess:switch:4" in cbs and "sess:new" in cbs
    assert "sess:del:4" in cbs and "sess:del:5" in cbs
