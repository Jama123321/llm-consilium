from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "proxy" / "config.yaml"
SERVER_PATH = REPO_ROOT / "consilium_mcp" / "server.py"

CONFIG_DIR = Path.home() / ".config" / "consilium"
PID_PATH = CONFIG_DIR / "proxy.pid"
LOG_PATH = CONFIG_DIR / "proxy.log"
SYSTEMD_USER_DIR = Path.home() / ".config" / "systemd" / "user"

PROXY_HOST = "127.0.0.1"
PROXY_PORT = 4000


def venv_python() -> Path:
    return Path(sys.executable)


def litellm_exe() -> Path:
    name = "litellm.exe" if os.name == "nt" else "litellm"
    return Path(sys.executable).parent / name
