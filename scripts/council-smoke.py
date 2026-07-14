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
    ask = await o.ask("In one word, is 17 prime? Answer yes or no.")
    print(f"[ask] model={ask.model_used} note={ask.note}\n  -> {ask.answer.strip()[:120]}")
    council = await o.council("Name one concrete risk of free-tier LLM routing and why.")
    print(f"[council] mode={council.mode} judge={council.judge_used}")
    for a in council.per_member:
        print(f"  {'ok ' if a.ok else 'ABS'} {a.alias}: {a.detail}")
    print(f"  -> {council.answer.strip()[:200]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
