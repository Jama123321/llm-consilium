from consilium_chat import config


def test_defaults():
    s = config.load_settings(env={})
    assert s.host == "127.0.0.1" and s.port == 8080
    assert s.chat_db_path.endswith("chat.db")
    assert s.context_turns == 8 and s.context_char_budget == 6000


def test_env_overrides():
    s = config.load_settings(env={"CONSILIUM_CHAT_HOST": "0.0.0.0", "CONSILIUM_CHAT_PORT": "9000",
                                  "CONSILIUM_CHAT_TURNS": "4"})
    assert s.host == "0.0.0.0" and s.port == 9000 and s.context_turns == 4
