from pathlib import Path

from council import registry

CONFIG = Path(__file__).resolve().parents[1] / "proxy" / "config.yaml"


def _members():
    return {m.alias: m for m in registry.load_members(CONFIG)}


def test_loads_all_thirteen_members():
    assert set(_members()) == {
        "council/cerebras-glm-4.7", "council/cerebras-gpt-oss-120b",
        "council/groq-llama-70b", "council/groq-gpt-oss-120b",
        "council/cloudflare-llama-70b",
        "council/github-gpt-4.1", "council/github-gpt-4.1-mini",
        "council/mistral-large", "council/mistral-codestral",
        "council/sambanova-deepseek-v3", "council/sambanova-llama-70b",
        "council/nvidia-deepseek-r1", "council/nvidia-llama-70b",
    }


def test_tier_b_providers_tagged_b():
    m = _members()
    for alias in ["council/mistral-large", "council/sambanova-deepseek-v3",
                  "council/nvidia-deepseek-r1"]:
        assert m[alias].privacy_tier == "B"
    assert m["council/github-gpt-4.1"].privacy_tier == "A"


def test_capabilities_and_scores_parsed():
    glm = _members()["council/cerebras-glm-4.7"]
    assert glm.privacy_tier == "A"
    assert glm.scores["reasoning"] == 5
    assert glm.strength == 5
    assert "reasoning" in glm.capabilities


def test_provider_family_derived():
    m = _members()
    assert m["council/cerebras-glm-4.7"].provider_family == "cerebras"
    assert m["council/groq-gpt-oss-120b"].provider_family == "groq"
    assert m["council/cloudflare-llama-70b"].provider_family == "cloudflare"


def test_legacy_strength_capabilities_synthesized(tmp_path):
    cfg = tmp_path / "legacy.yaml"
    cfg.write_text(
        "model_list:\n"
        "  - model_name: council/legacy\n"
        "    litellm_params: {model: groq/x, rpm: 7}\n"
        "    model_info: {privacy_tier: A, strength: 4, capabilities: [reasoning, code]}\n"
    )
    m = {x.alias: x for x in registry.load_members(cfg)}["council/legacy"]
    assert m.scores == {"reasoning": 4, "code": 4}
    assert m.strength == 4 and m.provider_family == "groq"


def test_rpm_defaults_when_absent():
    # cloudflare alias has no rpm in config -> default 10
    assert _members()["council/cloudflare-llama-70b"].rpm == 10


def test_daily_caps_parsed():
    m = _members()
    assert m["council/groq-llama-70b"].rpd == 1000
    assert m["council/groq-llama-70b"].tpd is None
    assert m["council/cloudflare-llama-70b"].tpd == 10000
    assert m["council/cloudflare-llama-70b"].rpd is None
    assert m["council/cerebras-glm-4.7"].tpd == 1000000


def test_available_env_keys_reads_process_and_file(tmp_path, monkeypatch):
    monkeypatch.setenv("FOO_KEY", "x")
    monkeypatch.delenv("BAR_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text("BAR_KEY=y\nEMPTY_KEY=\n# comment\n")
    keys = registry.available_env_keys(env)
    assert "FOO_KEY" in keys and "BAR_KEY" in keys
    assert "EMPTY_KEY" not in keys


def test_load_members_filters_missing_keys():
    # Only Cerebras/Groq keys "available" -> Cloudflare + all Tier-B drop out.
    keys = {"CEREBRAS_API_KEY", "GROQ_API_KEY"}
    aliases = {m.alias for m in registry.load_members(CONFIG, available_keys=keys)}
    assert "council/cerebras-glm-4.7" in aliases
    assert "council/groq-llama-70b" in aliases
    assert "council/cloudflare-llama-70b" not in aliases  # needs CLOUDFLARE_*
    assert "council/mistral-large" not in aliases
    assert "council/nvidia-deepseek-r1" not in aliases


def test_load_members_no_filter_returns_all():
    assert len(registry.load_members(CONFIG)) == 13
