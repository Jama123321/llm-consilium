from pathlib import Path

from council import registry

CONFIG = Path(__file__).resolve().parents[1] / "proxy" / "config.yaml"


def _members():
    return {m.alias: m for m in registry.load_members(CONFIG)}


def test_loads_all_five_members():
    assert set(_members()) == {
        "council/cerebras-glm-4.7",
        "council/cerebras-gpt-oss-120b",
        "council/groq-llama-70b",
        "council/groq-gpt-oss-120b",
        "council/cloudflare-llama-70b",
    }


def test_capabilities_and_strength_parsed():
    glm = _members()["council/cerebras-glm-4.7"]
    assert glm.privacy_tier == "A"
    assert glm.strength == 5
    assert "reasoning" in glm.capabilities


def test_rpm_defaults_when_absent():
    # cloudflare alias has no rpm in config -> default 10
    assert _members()["council/cloudflare-llama-70b"].rpm == 10
