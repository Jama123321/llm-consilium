from __future__ import annotations

import os
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from council import orchestrator as orch  # noqa: E402
from council.types import AskResult, CouncilResult  # noqa: E402

mcp = FastMCP("consilium")
_orch: orch.Orchestrator | None = None


def _load_master_key() -> str:
    key = os.environ.get("LITELLM_MASTER_KEY")
    if key:
        return key
    env_file = Path.home() / ".config" / "consilium" / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("LITELLM_MASTER_KEY="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("LITELLM_MASTER_KEY not found in env or ~/.config/consilium/.env")


def _get_orch() -> orch.Orchestrator:
    global _orch
    if _orch is None:
        _orch = orch.build(api_key=_load_master_key())
    return _orch


def _shape_ask(r: AskResult) -> dict:
    return {
        "answer": r.answer,
        "model_used": r.model_used,
        "capability": r.capability,
        "note": r.note,
    }


def _shape_council(r: CouncilResult) -> dict:
    return {
        "answer": r.answer,
        "mode": r.mode,
        "judge_used": r.judge_used,
        "disagreements": r.disagreements,
        "per_member": [
            {"alias": a.alias, "ok": a.ok, "detail": a.detail, "answer": a.answer}
            for a in r.per_member
        ],
    }


@mcp.tool()
async def ask(
    prompt: str, model: str | None = None, capability: str | None = None,
    sensitivity: str = "sensitive",
) -> dict:
    """Ask one best-fit free model (auto-routed) or a specific model.

    sensitivity: "sensitive" (Tier-A only, default) or "public" (A+B).
    """
    return _shape_ask(
        await _get_orch().ask(prompt, model=model, capability=capability, sensitivity=sensitivity)
    )


@mcp.tool()
async def council(prompt: str, sensitivity: str = "sensitive") -> dict:
    """Convene the council: fan out to diverse free models and aggregate.

    sensitivity: "sensitive" (Tier-A only, default) or "public" (A+B).
    """
    return _shape_council(await _get_orch().council(prompt, sensitivity=sensitivity))


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
