from __future__ import annotations

from pathlib import Path

import yaml

from council.types import Member


def _derive_family(model: str) -> str:
    if model.startswith("openai/@cf/"):  # Cloudflare Workers AI shim
        return "cloudflare"
    return model.split("/", 1)[0] if "/" in model else model


def _scores(info: dict) -> dict[str, int]:
    raw = info.get("scores")
    if isinstance(raw, dict) and raw:
        return {str(k): int(v) for k, v in raw.items()}
    # Legacy fallback: flat strength + capabilities list.
    strength = int(info.get("strength", 1))
    caps = info.get("capabilities", ["general"])
    return {str(c): strength for c in caps}


def load_members(config_path: str | Path) -> list[Member]:
    data = yaml.safe_load(Path(config_path).read_text())
    members: list[Member] = []
    for entry in data.get("model_list", []):
        info = entry.get("model_info") or {}
        params = entry.get("litellm_params") or {}
        rpd = info.get("rpd")
        tpd = info.get("tpd")
        family = info.get("provider_family") or _derive_family(str(params.get("model", "")))
        members.append(
            Member(
                alias=entry["model_name"],
                privacy_tier=info.get("privacy_tier", "B"),
                scores=_scores(info),
                rpm=int(params.get("rpm", 10)),
                provider_family=family,
                rpd=int(rpd) if rpd is not None else None,
                tpd=int(tpd) if tpd is not None else None,
            )
        )
    return members
