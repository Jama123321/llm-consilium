from __future__ import annotations

from pathlib import Path

import yaml

from council.types import Member


def load_members(config_path: str | Path) -> list[Member]:
    data = yaml.safe_load(Path(config_path).read_text())
    members: list[Member] = []
    for entry in data.get("model_list", []):
        info = entry.get("model_info") or {}
        params = entry.get("litellm_params") or {}
        members.append(
            Member(
                alias=entry["model_name"],
                privacy_tier=info.get("privacy_tier", "B"),
                capabilities=tuple(info.get("capabilities", ["general"])),
                strength=int(info.get("strength", 1)),
                rpm=int(params.get("rpm", 10)),
            )
        )
    return members
