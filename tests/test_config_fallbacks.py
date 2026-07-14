from pathlib import Path

import yaml

from council import registry

CONFIG = Path(__file__).resolve().parents[1] / "proxy" / "config.yaml"


def test_router_settings_have_retry_and_cooldown():
    data = yaml.safe_load(CONFIG.read_text())
    rs = data["router_settings"]
    assert rs["allowed_fails"] >= 1
    assert rs["cooldown_time"] >= 1
    assert "retry_policy" in rs


def test_fallbacks_never_cross_tiers():
    data = yaml.safe_load(CONFIG.read_text())
    tier = {m.alias: m.privacy_tier for m in registry.load_members(CONFIG)}
    for mapping in data["router_settings"].get("fallbacks", []):
        for primary, targets in mapping.items():
            for target in targets:
                assert tier[primary] == tier[target], (
                    f"{primary} ({tier[primary]}) must not fall back to "
                    f"{target} ({tier[target]})"
                )
