from fastapi.testclient import TestClient

from consilium_chat.app import create_app, is_configured


def test_is_configured_false_when_empty():
    assert is_configured({}) is False


def test_is_configured_true_when_a_provider_ready():
    # Groq needs only GROQ_API_KEY
    assert is_configured({"GROQ_API_KEY": "x"}) is True


def test_is_configured_false_on_partial_multivar():
    # Cloudflare needs BOTH CLOUDFLARE_API_TOKEN and CLOUDFLARE_API_BASE
    assert is_configured({"CLOUDFLARE_API_TOKEN": "x"}) is False


def test_status_has_configured_and_provider_metadata(tmp_path, monkeypatch):
    monkeypatch.setenv("CONSILIUM_CHAT_DB", str(tmp_path / "c.db"))
    body = TestClient(create_app(service=object())).get("/api/status").json()
    assert "configured" in body and isinstance(body["configured"], bool)
    assert body["providers"], "expected provider rows"
    row = body["providers"][0]
    assert "env_vars" in row and isinstance(row["env_vars"], list)
    assert "signup" in row
