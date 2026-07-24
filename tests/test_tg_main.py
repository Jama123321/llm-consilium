from consilium_tg import __main__ as m


def _settings(token):
    from consilium_tg.config import Settings
    return Settings(bot_token=token)


def test_main_refuses_without_token(monkeypatch, capsys):
    monkeypatch.setattr(m, "load_settings", lambda: _settings(""))
    rc = m.main([])
    assert rc == 1 and "TELEGRAM_BOT_TOKEN" in capsys.readouterr().out


def test_main_runs_with_token(monkeypatch):
    called = {}
    monkeypatch.setattr(m, "load_settings", lambda: _settings("123:abc"))
    monkeypatch.setattr(m, "build_application", lambda: "APP")
    monkeypatch.setattr(m, "_run", lambda app: called.setdefault("app", app))
    assert m.main([]) == 0 and called["app"] == "APP"
