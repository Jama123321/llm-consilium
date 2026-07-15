from __future__ import annotations

import sys

from consilium import doctor, init, service, setup

_USAGE = (
    "usage: python -m consilium "
    "{init|start [--foreground]|stop|status|mcp-register|install-service|doctor}"
)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    cmd = args[0] if args else ""
    rest = args[1:]
    if cmd == "init":
        return init.run()
    if cmd == "start":
        return service.start(foreground="--foreground" in rest)
    if cmd == "stop":
        return service.stop()
    if cmd == "status":
        return service.status()
    if cmd == "mcp-register":
        return setup.mcp_register()
    if cmd == "install-service":
        return setup.install_service()
    if cmd == "doctor":
        return doctor.doctor()
    print(_USAGE)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
