from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).resolve().parents[1] / "proxy" / "config.yaml"
EXPECTED_ALIASES = {
    "council/cerebras-qwen-235b",
    "council/cerebras-llama-70b",
    "council/groq-llama-70b",
    "council/groq-gpt-oss-120b",
    "council/cloudflare-llama-70b",
}

# Tier-A safety contract: every alias must route to a Tier-A provider prefix.
# `openai/` is the LiteLLM shim for Cloudflare Workers AI and is Tier-A ONLY
# because api_base points at Cloudflare — without api_base it would silently
# route to real OpenAI (Tier-B). These two tests make that invariant
# regression-proof at the config layer.
ALLOWED_MODEL_PREFIXES = ("cerebras/", "groq/", "openai/")


def _load():
    return yaml.safe_load(CONFIG_PATH.read_text())


def test_expected_aliases_present():
    cfg = _load()
    names = {m["model_name"] for m in cfg["model_list"]}
    assert names == EXPECTED_ALIASES


def test_every_alias_tagged_tier_a():
    cfg = _load()
    for m in cfg["model_list"]:
        assert m["model_info"]["privacy_tier"] == "A", m["model_name"]


def test_no_literal_secrets():
    cfg = _load()
    for m in cfg["model_list"]:
        params = m["litellm_params"]
        assert params["api_key"].startswith("os.environ/"), m["model_name"]
        if "api_base" in params:
            assert params["api_base"].startswith("os.environ/"), m["model_name"]


def test_master_key_via_env():
    cfg = _load()
    assert cfg["general_settings"]["master_key"] == "os.environ/LITELLM_MASTER_KEY"


def test_all_aliases_use_tier_a_provider_prefixes():
    cfg = _load()
    for m in cfg["model_list"]:
        model = m["litellm_params"]["model"]
        assert model.startswith(ALLOWED_MODEL_PREFIXES), m["model_name"]


def test_openai_shim_aliases_pin_api_base():
    cfg = _load()
    for m in cfg["model_list"]:
        params = m["litellm_params"]
        if params["model"].startswith("openai/"):
            assert "api_base" in params, m["model_name"]
            assert params["api_base"].startswith("os.environ/"), m["model_name"]
