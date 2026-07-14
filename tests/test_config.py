from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).resolve().parents[1] / "proxy" / "config.yaml"

# Expected tier per alias. Pinning the whole map makes mistagging a training
# provider (Tier B) as Tier A a hard test failure — a privacy regression guard.
EXPECTED_TIER = {
    "council/cerebras-glm-4.7": "A",
    "council/cerebras-gpt-oss-120b": "A",
    "council/groq-llama-70b": "A",
    "council/groq-gpt-oss-120b": "A",
    "council/cloudflare-llama-70b": "A",
    "council/github-gpt-4.1": "A",
    "council/github-gpt-4.1-mini": "A",
    "council/mistral-large": "B",
    "council/mistral-codestral": "B",
    "council/sambanova-deepseek-v3": "B",
    "council/sambanova-llama-70b": "B",
    "council/nvidia-deepseek-r1": "B",
    "council/nvidia-llama-70b": "B",
}
EXPECTED_ALIASES = set(EXPECTED_TIER)

# Tier-A safety contract: a Tier-A alias must route through a Tier-A provider
# prefix, so a Tier-A tag can never silently route through a training provider.
# `github/` (GitHub Models, no-train) and the `openai/` Cloudflare shim are
# Tier-A; `openai/` is Tier-A ONLY because api_base pins Cloudflare — enforced
# by test_openai_shim_aliases_pin_api_base.
TIER_A_MODEL_PREFIXES = ("cerebras/", "groq/", "openai/", "github/")


def _load():
    return yaml.safe_load(CONFIG_PATH.read_text())


def test_expected_aliases_present():
    cfg = _load()
    names = {m["model_name"] for m in cfg["model_list"]}
    assert names == EXPECTED_ALIASES


def test_aliases_tagged_expected_tier():
    cfg = _load()
    for m in cfg["model_list"]:
        assert m["model_info"]["privacy_tier"] == EXPECTED_TIER[m["model_name"]], m["model_name"]


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


def test_tier_a_aliases_use_tier_a_provider_prefixes():
    cfg = _load()
    for m in cfg["model_list"]:
        if m["model_info"]["privacy_tier"] == "A":
            model = m["litellm_params"]["model"]
            assert model.startswith(TIER_A_MODEL_PREFIXES), m["model_name"]


def test_openai_shim_aliases_pin_api_base():
    cfg = _load()
    for m in cfg["model_list"]:
        params = m["litellm_params"]
        if params["model"].startswith("openai/"):
            assert "api_base" in params, m["model_name"]
            assert params["api_base"].startswith("os.environ/"), m["model_name"]
