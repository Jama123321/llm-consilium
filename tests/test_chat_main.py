from fastapi.testclient import TestClient

from consilium_chat.app import create_app


def test_app_serves_index_and_status(tmp_path, monkeypatch):
    monkeypatch.setenv("CONSILIUM_CHAT_DB", str(tmp_path / "c.db"))

    class FakeService:
        def list_models(self):
            return []

    app = create_app(service=FakeService())
    client = TestClient(app)
    assert client.get("/").status_code == 200
    r = client.get("/api/status")
    assert r.status_code == 200
    body = r.json()
    assert "providers" in body and "proxy_up" in body and "total_cost_usd" in body


def test_app_builds_with_guarded_service(tmp_path, monkeypatch):
    # Even if CouncilService.build() cannot connect, app creation must not raise.
    monkeypatch.setenv("CONSILIUM_CHAT_DB", str(tmp_path / "c.db"))
    app = create_app()
    assert app is not None
    assert TestClient(app).get("/api/status").status_code == 200
