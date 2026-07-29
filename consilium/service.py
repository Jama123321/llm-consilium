from __future__ import annotations

import os
import signal
import socket
import subprocess

from consilium import env_file, paths


def proxy_command() -> list[str]:
    return [
        str(paths.litellm_exe()), "--config", str(paths.CONFIG_PATH),
        "--host", paths.PROXY_HOST, "--port", str(paths.PROXY_PORT),
    ]


def proxy_env(env_path=env_file.DEFAULT_ENV_PATH) -> dict[str, str]:
    env = dict(os.environ)
    env.update(env_file.load(env_path))
    return env


def _read_pid() -> int | None:
    try:
        return int(paths.PID_PATH.read_text().strip())
    except (OSError, ValueError):
        return None


def _write_pid(pid: int) -> None:
    paths.PID_PATH.parent.mkdir(parents=True, exist_ok=True)
    paths.PID_PATH.write_text(str(pid))


def _is_alive(pid: int) -> bool:
    if os.name == "posix":
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True
    out = subprocess.run(  # noqa: S603 - fixed Windows liveness probe, no user input
        # noqa reason: "tasklist" is a trusted system utility on Windows
        ["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True  # noqa: S607
    )
    return str(pid) in out.stdout


def port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _terminate(pid: int) -> None:
    if os.name == "posix":
        os.kill(pid, signal.SIGTERM)
    else:
        subprocess.run(  # noqa: S603 - fixed Windows terminate command, no user input
            # noqa reason: "taskkill" is a trusted system utility on Windows
            ["taskkill", "/PID", str(pid), "/F"], capture_output=True  # noqa: S607
        )


def _exec(cmd: list[str], env: dict[str, str]) -> int:  # pragma: no cover - replaces the process
    os.execvpe(cmd[0], cmd, env)  # noqa: S606 - intentional proxy launch; cmd built internally
    return 0


def start(*, foreground: bool = False, spawn=subprocess.Popen, exec_fn=_exec,
          is_alive=_is_alive, env_path=env_file.DEFAULT_ENV_PATH, echo=print) -> int:
    cmd = proxy_command()
    env = proxy_env(env_path)
    if foreground:
        return exec_fn(cmd, env)
    pid = _read_pid()
    if pid and is_alive(pid):
        echo(f"already running (pid {pid})")
        return 0
    paths.LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    log = open(paths.LOG_PATH, "ab")
    kwargs: dict = {"env": env, "stdout": log, "stderr": log}
    if os.name == "posix":
        kwargs["start_new_session"] = True
    else:
        kwargs["creationflags"] = (
            subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        )
    proc = spawn(cmd, **kwargs)
    _write_pid(proc.pid)
    echo(f"started (pid {proc.pid}) — logs: {paths.LOG_PATH}")
    return 0


def stop(*, terminate=_terminate, echo=print) -> int:
    pid = _read_pid()
    if not pid:
        echo("not running")
        return 0
    terminate(pid)
    paths.PID_PATH.unlink(missing_ok=True)
    echo(f"stopped (pid {pid})")
    return 0


def status(*, is_alive=_is_alive, port_open=port_open, echo=print) -> int:
    pid = _read_pid()
    alive = bool(pid) and is_alive(pid)
    echo(f"process: {'running (pid ' + str(pid) + ')' if alive else 'stopped'}")
    listening = port_open(paths.PROXY_HOST, paths.PROXY_PORT)
    echo(f"port {paths.PROXY_PORT}: {'listening' if listening else 'closed'}")
    return 0
