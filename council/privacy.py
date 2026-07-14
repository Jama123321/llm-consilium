from __future__ import annotations

import re

from council.errors import PrivacyRefusal
from council.types import Member

_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9]{16,}"),
    re.compile(r"\bcsk-[A-Za-z0-9]{16,}"),
    re.compile(r"\bgsk_[A-Za-z0-9]{16,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?im)^\s*[A-Z0-9_]*(?:API_KEY|SECRET|TOKEN|PASSWORD)\s*="),
)


def scan_secrets(prompt: str) -> None:
    for pat in _SECRET_PATTERNS:
        if pat.search(prompt):
            raise PrivacyRefusal(
                "prompt appears to contain a secret; strip credentials before "
                "consulting the council"
            )


def allowed_members(members: list[Member], sensitivity: str) -> list[Member]:
    if sensitivity == "public":
        return list(members)
    return [m for m in members if m.privacy_tier == "A"]
