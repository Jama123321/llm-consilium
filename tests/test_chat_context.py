from consilium_chat.context import build_prompt


def test_includes_recent_turns_and_new_message():
    hist = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]
    p = build_prompt(hist, "c", turns=8, char_budget=6000)
    assert "User: a" in p and "Assistant: b" in p and p.rstrip().endswith("c")


def test_turn_window_limits_history():
    hist = [{"role": "user", "content": f"m{i}"} for i in range(20)]
    p = build_prompt(hist, "new", turns=3, char_budget=6000)
    assert "m19" in p and "m0" not in p


def test_char_budget_trims_oldest():
    hist = [{"role": "user", "content": "X" * 100} for _ in range(10)]
    p = build_prompt(hist, "q", turns=10, char_budget=250)
    assert len(p) <= 400  # preamble + a couple of turns + new msg, oldest dropped
