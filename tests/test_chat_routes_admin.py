from fastapi import FastAPI
from fastapi.testclient import TestClient

from consilium_chat.routes_admin import admin_router


def _app(state):
    app = FastAPI()
    for k, v in state.items():
        setattr(app.state, k, v)
    app.include_router(admin_router())
    return app


def test_status_shape():
    app = _app({"status_provider": lambda: {"providers": [{"name": "Groq", "tier": "A",
               "ready": True}], "proxy_up": False, "usage": [], "total_cost_usd": 0.0}})
    r = TestClient(app).get("/api/status")
    assert r.status_code == 200 and r.json()["providers"][0]["name"] == "Groq"


def test_keys_saved_and_masked(tmp_path):
    saved = {}
    app = _app({"save_keys": lambda body: {"GROQ_API_KEY": "set (...cdef)"} if
                saved.update(body) is None else {}})
    r = TestClient(app).post("/api/keys", json={"GROQ_API_KEY": "abcdef"})
    assert r.status_code == 200 and "cdef" in r.json()["GROQ_API_KEY"]
    assert saved == {"GROQ_API_KEY": "abcdef"} and "abcdef" not in r.text


def test_proxy_start_success():
    app = _app({"proxy_start": lambda: {"ok": True, "pid": 4242}})
    r = TestClient(app).post("/api/proxy/start")
    assert r.status_code == 200 and r.json() == {"ok": True, "pid": 4242}


def test_proxy_start_failure_dict_returns_503():
    payload = {"ok": False, "error": "port in use"}
    app = _app({"proxy_start": lambda: payload})
    r = TestClient(app).post("/api/proxy/start")
    assert r.status_code == 503 and r.json() == payload


def test_proxy_start_falsy_returns_503():
    app = _app({"proxy_start": lambda: None})
    r = TestClient(app).post("/api/proxy/start")
    assert r.status_code == 503 and r.json() == {"ok": False}


def test_proxy_stop():
    app = _app({"proxy_stop": lambda: {"ok": True, "stopped": True}})
    r = TestClient(app).post("/api/proxy/stop")
    assert r.status_code == 200 and r.json() == {"ok": True, "stopped": True}
