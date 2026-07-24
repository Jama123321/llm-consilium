from consilium_tg import config


def test_defaults():
    s = config.load_settings(env={})
    assert s.bot_token == "" and s.owner_id is None
    assert s.db_path.endswith("tg.db") and s.access_path.endswith("tg_access.json")
    assert s.context_turns == 8 and s.context_char_budget == 6000
    assert s.default_sensitivity == "sensitive"


def test_env_overrides():
    s = config.load_settings(env={"TELEGRAM_BOT_TOKEN": "tok", "TELEGRAM_OWNER_ID": "42",
                                  "CONSILIUM_TG_TURNS": "4"})
    assert s.bot_token == "tok" and s.owner_id == 42 and s.context_turns == 4
