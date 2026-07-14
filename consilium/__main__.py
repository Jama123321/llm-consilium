from __future__ import annotations

import sys

from consilium import init


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args and args[0] == "init":
        return init.run()
    print("usage: python -m consilium init")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
