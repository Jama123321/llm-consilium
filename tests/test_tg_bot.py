from consilium_tg.bot import build_application
from consilium_tg.config import Settings


class FakeService:
    def list_models(self):
        return []


def test_build_application_wires_bot_data(tmp_path):
    s = Settings(bot_token="123:abc", owner_id=7, db_path=str(tmp_path / "tg.db"),
                 access_path=str(tmp_path / "acc.json"))
    app = build_application(settings=s, service=FakeService())
    assert app.bot_data["settings"].owner_id == 7
    assert app.bot_data["store"] is not None and app.bot_data["access"].is_owner(7)
    # all handlers registered in the default group (>= 6)
    assert len(app.handlers[0]) >= 6
