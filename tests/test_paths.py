import os
import sys
from pathlib import Path

from consilium import paths


def test_repo_paths_absolute_and_exist():
    assert paths.REPO_ROOT.is_absolute()
    assert paths.CONFIG_PATH.name == "config.yaml" and paths.CONFIG_PATH.exists()
    assert paths.SERVER_PATH.name == "server.py" and paths.SERVER_PATH.exists()


def test_venv_python_and_litellm_sibling():
    assert paths.venv_python() == Path(sys.executable)
    assert paths.litellm_exe().parent == Path(sys.executable).parent
    assert paths.litellm_exe().name == ("litellm.exe" if os.name == "nt" else "litellm")


def test_proxy_host_port_and_dirs():
    assert paths.PROXY_HOST == "127.0.0.1" and paths.PROXY_PORT == 4000
    assert paths.PID_PATH.name == "proxy.pid" and paths.LOG_PATH.name == "proxy.log"
    assert paths.SYSTEMD_USER_DIR.parts[-2:] == ("systemd", "user")
