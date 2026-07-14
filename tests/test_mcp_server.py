import pytest

from consilium_mcp import server
from council.types import AskResult, CouncilResult, MemberAnswer


def test_load_master_key_from_env(monkeypatch):
    monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-fromenv")
    assert server._load_master_key() == "sk-fromenv"


def test_load_master_key_from_file(monkeypatch, tmp_path):
    monkeypatch.delenv("LITELLM_MASTER_KEY", raising=False)
    home = tmp_path
    monkeypatch.setattr(server.Path, "home", staticmethod(lambda: home))
    target = home / ".config" / "consilium" / ".env"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("GROQ_API_KEY=x\nLITELLM_MASTER_KEY=sk-fromfile\n")
    assert server._load_master_key() == "sk-fromfile"


def test_load_master_key_missing_raises(monkeypatch, tmp_path):
    monkeypatch.delenv("LITELLM_MASTER_KEY", raising=False)
    monkeypatch.setattr(server.Path, "home", staticmethod(lambda: tmp_path))
    with pytest.raises(RuntimeError):
        server._load_master_key()


def test_shape_ask():
    r = AskResult(answer="a", model_used="council/x", capability="code", note="routed: code")
    assert server._shape_ask(r) == {
        "answer": "a", "model_used": "council/x", "capability": "code", "note": "routed: code",
    }


def test_shape_council():
    r = CouncilResult(
        answer="merged",
        per_member=[MemberAnswer("council/x", True, "hi", "ok")],
        disagreements="none",
        judge_used="council/x",
        mode="judge",
    )
    out = server._shape_council(r)
    assert out["answer"] == "merged" and out["mode"] == "judge"
    assert out["per_member"][0] == {
        "alias": "council/x", "ok": True, "detail": "ok", "answer": "hi",
    }
