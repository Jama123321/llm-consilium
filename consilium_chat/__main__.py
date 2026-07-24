from __future__ import annotations

import argparse

from consilium_chat.app import create_app
from consilium_chat.config import load_settings


def _serve(app, host: str, port: int) -> None:
    import uvicorn

    uvicorn.run(app, host=host, port=port)


def main(argv=None) -> None:
    settings = load_settings()
    parser = argparse.ArgumentParser(prog="consilium_chat")
    parser.add_argument("--host", default=settings.host)
    parser.add_argument("--port", type=int, default=settings.port)
    args = parser.parse_args(argv)

    app = create_app()
    _serve(app, args.host, args.port)


if __name__ == "__main__":
    main()
