#!/usr/bin/env python3
"""Print today's per-member Consilium usage vs daily caps."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from council import registry, usage  # noqa: E402

CONFIG = Path(__file__).resolve().parents[1] / "proxy" / "config.yaml"


def main() -> int:
    members = registry.load_members(CONFIG)
    rows = usage.summary(members, usage.UsageStore().counts())
    header = f"{'alias':32} {'tier':4} {'req':>6} {'tokens':>10} {'rpd':>8} {'tpd':>10}  flag"
    print(header)
    print("-" * len(header))
    for r in rows:
        flag = "EXHAUSTED" if r["exhausted"] else ""
        print(
            f"{r['alias']:32} {r['tier']:4} {r['requests']:>6} {r['tokens']:>10} "
            f"{str(r['rpd'] if r['rpd'] is not None else '-'):>8} "
            f"{str(r['tpd'] if r['tpd'] is not None else '-'):>10}  {flag}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
