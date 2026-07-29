#!/usr/bin/env python3
"""Live smoke for the council orchestrator against the running proxy.

Requires the proxy up (bash scripts/run-proxy.sh) and LITELLM_MASTER_KEY in env
(set -a; source ~/.config/consilium/.env; set +a). Not part of the CI gate.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from council import orchestrator as orch  # noqa: E402


async def _main() -> int:
    key = os.environ.get("LITELLM_MASTER_KEY", "")
    if not key:
        print("ERROR: LITELLM_MASTER_KEY not set", file=sys.stderr)
        return 2
    o = orch.build(api_key=key)

    # 1) ping each active member with a 1-token question
    from council import registry
    present = registry.available_env_keys()
    members = registry.load_members("proxy/config.yaml", available_keys=present)
    print(f"[active members] {len(members)}: {[m.alias for m in members]}")
    for m in members:
        try:
            r = await o.ask("Reply with the single word: ok", model=m.alias,
                            sensitivity="public")
            print(f"  ok  {m.alias}: {r.answer.strip()[:40]}")
        except Exception as exc:  # noqa: BLE001 - smoke: report and continue
            print(f"  ERR {m.alias}: {exc.__class__.__name__}: {exc}")

    # 2) public council may include Tier-B
    pub = await o.council("Name one risk of free-tier LLM routing.", sensitivity="public")
    print(f"[public council] note={pub.note}")
    for a in pub.per_member:
        print(f"  {'ok ' if a.ok else 'ABS'} {a.alias}")

    # 3) sensitive council must contact NO Tier-B member
    tier = {m.alias: m.privacy_tier for m in members}
    sen = await o.council("Explain one tradeoff of self-hosting an LLM proxy.",
                          sensitivity="sensitive")
    contacted_b = [a.alias for a in sen.per_member if tier.get(a.alias) == "B"]
    print(f"[sensitive council] note={sen.note} tier-B contacted={contacted_b}")
    assert not contacted_b, f"PRIVACY LEAK: Tier-B contacted on sensitive: {contacted_b}"  # noqa: S101 - smoke-test privacy check
    print("[tier isolation] OK — no Tier-B on sensitive")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
