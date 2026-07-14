from __future__ import annotations

import os
from pathlib import Path

DEFAULT_ENV_PATH = Path.home() / ".config" / "consilium" / ".env"

_TIER_A = (
    "CEREBRAS_API_KEY", "GROQ_API_KEY", "CLOUDFLARE_API_TOKEN",
    "CLOUDFLARE_API_BASE", "GITHUB_API_KEY",
)
_TIER_B = ("MISTRAL_API_KEY", "SAMBANOVA_API_KEY", "NVIDIA_NIM_API_KEY")
_KNOWN = set(_TIER_A) | set(_TIER_B) | {"LITELLM_MASTER_KEY"}


def load(path: str | Path = DEFAULT_ENV_PATH) -> dict[str, str]:
    values: dict[str, str] = {}
    p = Path(path)
    if not p.exists():
        return values
    for raw in p.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        values[key.strip()] = val.strip()
    return values


def _group(lines: list[str], title: str, keys, values: dict[str, str]) -> None:
    present = [k for k in keys if k in values]
    if not present:
        return
    lines.append(f"# {title}")
    lines.extend(f"{k}={values[k]}" for k in present)
    lines.append("")


def write(path: str | Path = DEFAULT_ENV_PATH, values: dict[str, str] | None = None) -> None:
    data = dict(values or {})
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Consilium secrets — managed by `python -m consilium init`. chmod 600.", ""]
    _group(lines, "Tier A (safe for any prompt — no-train)", _TIER_A, data)
    _group(lines, "Tier B (public prompts only)", _TIER_B, data)
    _group(lines, "Proxy auth", ("LITELLM_MASTER_KEY",), data)
    _group(lines, "Other", [k for k in data if k not in _KNOWN], data)
    p.write_text("\n".join(lines).rstrip() + "\n")
    if os.name == "posix":
        p.chmod(0o600)
