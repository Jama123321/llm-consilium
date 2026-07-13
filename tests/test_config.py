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
