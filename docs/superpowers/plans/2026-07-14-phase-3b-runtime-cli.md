# Phase 3b — Runtime CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the `consilium` package with cross-platform, path-agnostic runtime commands — `start`/`stop`/`status` (background proxy + PID), `mcp-register`, `install-service`, `doctor` — via `python -m consilium <cmd>`, and de-hardcode the remaining `/opt` paths.

**Architecture:** `consilium/paths.py` is the single source of truth for locations (derived from the module). `service.py` manages the proxy process; `setup.py` registers the MCP and generates the systemd unit; `doctor.py` diagnoses. Process spawning, signals, sockets, and subprocess runners are injected so tests are hermetic.

**Tech Stack:** Python 3.10, stdlib (`os`/`sys`/`signal`/`socket`/`subprocess`), pytest, ruff.

## Global Constraints

- Cross-platform (Linux + Windows); guard OS-specific calls. No bash in the runtime path.
- Every path derives from `paths.py` (module location / `$HOME`) — never hardcoded `/opt` or CWD.
- `start` loads `~/.config/consilium/.env` into the proxy subprocess env; never prints key values.
- Canonical launcher = `consilium start --foreground`; `consilium start` (bg) + systemd unit call it.
- Injected seams (`spawn`/`exec_fn`/`terminate`/`is_alive`/`port_open`/`runner`) → hermetic tests; no real proxy/network/`claude`/`systemctl`.
- Idempotent; non-destructive (don't force-replace the running deployed unit).
- Repo ruff enforces B905/I001/E501 (line-length 100). Python 3.10+; `ruff check .` clean + `pytest -q` green. Commits English imperative, no `Co-Authored-By`. Branch `phase-3b-runtime`.

## File map

- `consilium/paths.py`, `consilium/service.py`, `consilium/setup.py`, `consilium/doctor.py` — NEW.
- `consilium/__main__.py` — extend dispatch.
- `docs/usage-rule.md` — `mcp-register` instead of hardcoded `claude mcp add`.
- `deploy/consilium-proxy.service` — remove (superseded by generated unit).
- Tests: `tests/test_paths.py`, `tests/test_service.py`, `tests/test_setup.py`, `tests/test_doctor.py`, `tests/test_cli_main.py` — NEW.

---

### Task 1: `consilium/paths.py` (shared locations)

**Files:** Create `consilium/paths.py`, `tests/test_paths.py`.

**Interfaces:** Produces `REPO_ROOT`, `CONFIG_PATH`, `SERVER_PATH`, `CONFIG_DIR`, `PID_PATH`, `LOG_PATH`, `SYSTEMD_USER_DIR`, `PROXY_HOST`, `PROXY_PORT`, `venv_python()`, `litellm_exe()`.

- [ ] **Step 1: Write `tests/test_paths.py`**

```python
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
```

- [ ] **Step 2: Run — expect failure** — `.venv/bin/pytest tests/test_paths.py -q` (module missing).

- [ ] **Step 3: Implement `consilium/paths.py`**

```python
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
```

- [ ] **Step 4: Run — expect pass** — `.venv/bin/ruff check consilium/paths.py tests/test_paths.py && .venv/bin/pytest tests/test_paths.py -q`.

- [ ] **Step 5: Commit** — `git add consilium/paths.py tests/test_paths.py && git commit -m "feat(3b): shared path/location helpers for the runtime CLI"`

---

### Task 2: `consilium/service.py` (start/stop/status)

**Files:** Create `consilium/service.py`, `tests/test_service.py`.

**Interfaces:** Consumes `paths`, `env_file`. Produces `proxy_command()`, `proxy_env()`, `port_open()`, `start(*, foreground, spawn, exec_fn, is_alive, env_path, echo)`, `stop(*, terminate, echo)`, `status(*, is_alive, port_open, echo)`.

*(Depends only on Task 1; disjoint from Task 3 — may run in parallel with it.)*

- [ ] **Step 1: Write `tests/test_service.py`**

```python
import os

from consilium import env_file, paths, service


def test_proxy_command_shape():
    cmd = service.proxy_command()
    assert cmd[0].endswith("litellm") or cmd[0].endswith("litellm.exe")
    assert "--config" in cmd and str(paths.CONFIG_PATH) in cmd
    assert "--port" in cmd and "4000" in cmd


def test_proxy_env_merges_dotenv(tmp_path, monkeypatch):
    envf = tmp_path / ".env"
    env_file.write(envf, {"CEREBRAS_API_KEY": "csk-x", "LITELLM_MASTER_KEY": "sk-1"})
    monkeypatch.delenv("CEREBRAS_API_KEY", raising=False)
    merged = service.proxy_env(envf)
    assert merged["CEREBRAS_API_KEY"] == "csk-x" and "PATH" in merged  # dotenv over os.environ


def test_start_background_writes_pid(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "PID_PATH", tmp_path / "proxy.pid")
    monkeypatch.setattr(paths, "LOG_PATH", tmp_path / "proxy.log")

    class FakeProc:
        pid = 4242

    calls = {}

    def spawn(cmd, **kw):
        calls["cmd"] = cmd
        return FakeProc()

    rc = service.start(spawn=spawn, is_alive=lambda _p: False,
                       env_path=tmp_path / "missing.env", echo=lambda _m: None)
    assert rc == 0
    assert (tmp_path / "proxy.pid").read_text().strip() == "4242"
    assert calls["cmd"][0].endswith("litellm") or calls["cmd"][0].endswith("litellm.exe")


def test_start_background_noop_when_already_running(tmp_path, monkeypatch):
    pid_file = tmp_path / "proxy.pid"
    pid_file.write_text("999")
    monkeypatch.setattr(paths, "PID_PATH", pid_file)
    spawned = []
    service.start(spawn=lambda *a, **k: spawned.append(1), is_alive=lambda _p: True,
                  env_path=tmp_path / "x.env", echo=lambda _m: None)
    assert spawned == []  # did not spawn a second proxy


def test_start_foreground_uses_exec_fn():
    captured = {}
    service.start(foreground=True, exec_fn=lambda cmd, env: captured.update(cmd=cmd) or 0,
                  env_path="nope.env", echo=lambda _m: None)
    assert "--config" in captured["cmd"]


def test_stop_terminates_and_clears_pid(tmp_path, monkeypatch):
    pid_file = tmp_path / "proxy.pid"
    pid_file.write_text("321")
    monkeypatch.setattr(paths, "PID_PATH", pid_file)
    killed = []
    rc = service.stop(terminate=killed.append, echo=lambda _m: None)
    assert rc == 0 and killed == [321] and not pid_file.exists()


def test_stop_when_not_running(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "PID_PATH", tmp_path / "none.pid")
    assert service.stop(terminate=lambda _p: None, echo=lambda _m: None) == 0


def test_status_reports_injected(tmp_path, monkeypatch):
    pid_file = tmp_path / "proxy.pid"
    pid_file.write_text("55")
    monkeypatch.setattr(paths, "PID_PATH", pid_file)
    out = []
    service.status(is_alive=lambda _p: True, port_open=lambda _h, _p: True, echo=out.append)
    joined = "\n".join(out)
    assert "running" in joined and "listening" in joined
```

- [ ] **Step 2: Run — expect failure** — `.venv/bin/pytest tests/test_service.py -q`.

- [ ] **Step 3: Implement `consilium/service.py`**

```python
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
    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True)
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
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)


def _exec(cmd: list[str], env: dict[str, str]) -> int:  # pragma: no cover - replaces the process
    os.execvpe(cmd[0], cmd, env)
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
    echo(f"port {paths.PROXY_PORT}: {'listening' if port_open(paths.PROXY_HOST, paths.PROXY_PORT) else 'closed'}")
    return 0
```

Note: on non-Windows, `subprocess.DETACHED_PROCESS`/`CREATE_NEW_PROCESS_GROUP` don't exist — but that branch only runs when `os.name != "posix"`, so it's never evaluated on POSIX. Keep the attribute access inside the `else`.

- [ ] **Step 4: Run — expect pass** — `.venv/bin/ruff check consilium/service.py tests/test_service.py && .venv/bin/pytest tests/test_service.py -q`.

- [ ] **Step 5: Commit** — `git add consilium/service.py tests/test_service.py && git commit -m "feat(3b): cross-platform proxy start/stop/status"`

---

### Task 3: `consilium/setup.py` (mcp-register + install-service)

**Files:** Create `consilium/setup.py`, `tests/test_setup.py`.

**Interfaces:** Consumes `paths`. Produces `mcp_add_command()`, `mcp_remove_command()`, `mcp_register(*, runner, echo)`, `systemd_unit_text(python, repo_root)`, `install_service(*, runner, echo)`.

*(Depends only on Task 1; disjoint from Task 2 — may run in parallel with it.)*

- [ ] **Step 1: Write `tests/test_setup.py`**

```python
import subprocess
import sys

from consilium import paths, setup


def test_mcp_commands_use_absolute_paths():
    add = setup.mcp_add_command()
    assert add[:6] == ["claude", "mcp", "add", "--scope", "user", "consilium"]
    assert str(paths.venv_python()) in add and str(paths.SERVER_PATH) in add
    assert setup.mcp_remove_command()[:3] == ["claude", "mcp", "remove"]


def test_mcp_register_removes_then_adds():
    calls = []

    def runner(cmd, **kw):
        calls.append(cmd[:4])
        return subprocess.CompletedProcess(cmd, 0, "", "")

    assert setup.mcp_register(runner=runner, echo=lambda _m: None) == 0
    assert calls[0][:3] == ["claude", "mcp", "remove"]
    assert calls[1][:3] == ["claude", "mcp", "add"]


def test_systemd_unit_text_calls_foreground():
    unit = setup.systemd_unit_text("/venv/bin/python", "/home/u/repo")
    assert "ExecStart=/venv/bin/python -m consilium start --foreground" in unit
    assert "WorkingDirectory=/home/u/repo" in unit and "PYTHONPATH=/home/u/repo" in unit
    assert "WantedBy=default.target" in unit


def test_install_service_non_linux_prints_only(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    ran = []
    rc = setup.install_service(runner=lambda *a, **k: ran.append(a), echo=lambda _m: None)
    assert rc == 0 and ran == []  # no systemctl on non-Linux


def test_install_service_linux_writes_unit(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(paths, "SYSTEMD_USER_DIR", tmp_path / "user")
    ran = []
    rc = setup.install_service(runner=lambda cmd, **k: ran.append(cmd[0]), echo=lambda _m: None)
    assert rc == 0
    unit = (tmp_path / "user" / "consilium-proxy.service").read_text()
    assert "consilium start --foreground" in unit
    assert "systemctl" in ran and "loginctl" in ran
```

- [ ] **Step 2: Run — expect failure** — `.venv/bin/pytest tests/test_setup.py -q`.

- [ ] **Step 3: Implement `consilium/setup.py`**

```python
from __future__ import annotations

import subprocess
import sys

from consilium import paths


def mcp_add_command() -> list[str]:
    return [
        "claude", "mcp", "add", "--scope", "user", "consilium", "--",
        str(paths.venv_python()), str(paths.SERVER_PATH),
    ]


def mcp_remove_command() -> list[str]:
    return ["claude", "mcp", "remove", "--scope", "user", "consilium"]


def mcp_register(*, runner=subprocess.run, echo=print) -> int:
    runner(mcp_remove_command(), capture_output=True, text=True)  # ignore if absent
    result = runner(mcp_add_command(), capture_output=True, text=True)
    if result.returncode == 0:
        echo("registered consilium MCP (--scope user) — restart Claude Code to load it")
        return 0
    echo(f"mcp-register failed: {(result.stderr or '').strip()}")
    return 1


def systemd_unit_text(python: str, repo_root: str) -> str:
    return (
        "[Unit]\n"
        "Description=Consilium LiteLLM proxy (free-LLM council compute layer)\n"
        "After=network-online.target\n\n"
        "[Service]\n"
        "Type=simple\n"
        f"WorkingDirectory={repo_root}\n"
        f"Environment=PYTHONPATH={repo_root}\n"
        f"ExecStart={python} -m consilium start --foreground\n"
        "Restart=on-failure\n"
        "RestartSec=3\n\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )


def install_service(*, runner=subprocess.run, echo=print) -> int:
    if not sys.platform.startswith("linux"):
        echo(
            "Autostart isn't automated on this OS. Run `python -m consilium start` at "
            "login, or add a Task Scheduler task (Windows) running: "
            f"{paths.venv_python()} -m consilium start --foreground"
        )
        return 0
    unit_path = paths.SYSTEMD_USER_DIR / "consilium-proxy.service"
    unit_path.parent.mkdir(parents=True, exist_ok=True)
    unit_path.write_text(systemd_unit_text(str(paths.venv_python()), str(paths.REPO_ROOT)))
    runner(["systemctl", "--user", "daemon-reload"])
    runner(["systemctl", "--user", "enable", "--now", "consilium-proxy"])
    runner(["loginctl", "enable-linger"])
    echo(f"installed systemd --user unit: {unit_path}")
    return 0
```

- [ ] **Step 4: Run — expect pass** — `.venv/bin/ruff check consilium/setup.py tests/test_setup.py && .venv/bin/pytest tests/test_setup.py -q`.

- [ ] **Step 5: Commit** — `git add consilium/setup.py tests/test_setup.py && git commit -m "feat(3b): mcp-register + systemd install-service (path-agnostic)"`

---

### Task 4: `consilium/doctor.py`

**Files:** Create `consilium/doctor.py`, `tests/test_doctor.py`.

**Interfaces:** Consumes `paths`, `env_file`, `providers`, `service.port_open`. Produces `doctor(*, port_open, runner, env_path, echo) -> int`.

*(Depends on Task 1 + Task 2's `service.port_open`.)*

- [ ] **Step 1: Write `tests/test_doctor.py`**

```python
import subprocess

from consilium import doctor, env_file


def test_doctor_reports_keys_proxy_and_mcp(tmp_path):
    envf = tmp_path / ".env"
    env_file.write(envf, {"CEREBRAS_API_KEY": "csk-x"})  # cerebras ready, others dormant
    out = []

    def runner(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 0, "consilium: /path/to/server.py", "")

    rc = doctor.doctor(port_open=lambda _h, _p: True, runner=runner, env_path=envf,
                       echo=out.append)
    joined = "\n".join(out)
    assert rc == 0
    assert "Cerebras" in joined and "READY" in joined
    assert "dormant" in joined  # a provider without a key
    assert "up" in joined  # proxy reachable (injected True)
    assert "yes" in joined  # mcp registered (runner output contains "consilium")


def test_doctor_proxy_down_and_mcp_absent(tmp_path):
    envf = tmp_path / ".env"
    env_file.write(envf, {})
    out = []

    def runner(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 0, "", "")

    doctor.doctor(port_open=lambda _h, _p: False, runner=runner, env_path=envf, echo=out.append)
    joined = "\n".join(out)
    assert "DOWN" in joined and "no" in joined
```

- [ ] **Step 2: Run — expect failure** — `.venv/bin/pytest tests/test_doctor.py -q`.

- [ ] **Step 3: Implement `consilium/doctor.py`**

```python
from __future__ import annotations

import subprocess

from consilium import env_file, paths
from consilium.providers import PROVIDERS
from consilium.service import port_open as _default_port_open


def doctor(*, port_open=_default_port_open, runner=subprocess.run,
           env_path=env_file.DEFAULT_ENV_PATH, echo=print) -> int:
    env = env_file.load(env_path)
    echo("Providers:")
    for provider in PROVIDERS:
        ready = all(env.get(v) for v in provider.env_vars)
        echo(f"  {'READY  ' if ready else 'dormant'} {provider.name} [Tier {provider.tier}]")
    up = port_open(paths.PROXY_HOST, paths.PROXY_PORT)
    echo(f"Proxy {paths.PROXY_HOST}:{paths.PROXY_PORT}: {'up' if up else 'DOWN'}")
    try:
        result = runner(["claude", "mcp", "list"], capture_output=True, text=True)
        registered = "consilium" in (result.stdout or "")
    except Exception:  # noqa: BLE001 - doctor is best-effort diagnostics; never crash
        registered = False
    echo(f"MCP consilium registered: {'yes' if registered else 'no'}")
    return 0
```

- [ ] **Step 4: Run — expect pass** — `.venv/bin/ruff check consilium/doctor.py tests/test_doctor.py && .venv/bin/pytest tests/test_doctor.py -q`.

- [ ] **Step 5: Commit** — `git add consilium/doctor.py tests/test_doctor.py && git commit -m "feat(3b): consilium doctor diagnostics"`

---

### Task 5: Dispatch + de-hardcode

**Files:** Modify `consilium/__main__.py`, `docs/usage-rule.md`; delete `deploy/consilium-proxy.service`; create `tests/test_cli_main.py`.

**Interfaces:** Consumes `init`, `service`, `setup`, `doctor`.

- [ ] **Step 1: Write `tests/test_cli_main.py`**

```python
from consilium import __main__ as cli


def test_dispatch_start_foreground(monkeypatch):
    got = {}
    monkeypatch.setattr(cli.service, "start", lambda *, foreground=False: got.update(fg=foreground) or 0)
    assert cli.main(["start", "--foreground"]) == 0 and got["fg"] is True
    assert cli.main(["start"]) == 0 and got["fg"] is False


def test_dispatch_each_command(monkeypatch):
    seen = []
    monkeypatch.setattr(cli.service, "stop", lambda: seen.append("stop") or 0)
    monkeypatch.setattr(cli.service, "status", lambda: seen.append("status") or 0)
    monkeypatch.setattr(cli.setup, "mcp_register", lambda: seen.append("reg") or 0)
    monkeypatch.setattr(cli.setup, "install_service", lambda: seen.append("svc") or 0)
    monkeypatch.setattr(cli.doctor, "doctor", lambda: seen.append("doc") or 0)
    for cmd in ["stop", "status", "mcp-register", "install-service", "doctor"]:
        assert cli.main([cmd]) == 0
    assert seen == ["stop", "status", "reg", "svc", "doc"]


def test_unknown_command_returns_usage(capsys):
    assert cli.main(["bogus"]) == 2
    assert cli.main([]) == 2
```

- [ ] **Step 2: Run — expect failure** — `.venv/bin/pytest tests/test_cli_main.py -q`.

- [ ] **Step 3: Rewrite `consilium/__main__.py`**

```python
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
```

- [ ] **Step 4: De-hardcode `docs/usage-rule.md`**

Replace the "Registering the MCP server" `claude mcp add … /opt/…` bash block with:

```bash
python -m consilium mcp-register   # run from the cloned repo; paths are derived automatically
```

- [ ] **Step 5: Remove the superseded static unit**

```bash
git rm deploy/consilium-proxy.service
```
(It's a hardcoded template, superseded by `consilium install-service`; the installed unit on this machine is separate and untouched.)

- [ ] **Step 6: Run — expect pass (full gate)** — `.venv/bin/ruff check . && .venv/bin/pytest -q`.

- [ ] **Step 7: Commit** — `git add consilium/__main__.py tests/test_cli_main.py docs/usage-rule.md && git commit -m "feat(3b): CLI dispatch for runtime commands + de-hardcode paths"`

---

## Self-review

**Spec coverage:** paths → T1; start/stop/status (background PID, foreground exec, cross-platform) → T2; mcp-register + install-service (absolute paths, systemd unit, non-Linux guidance) → T3; doctor → T4; dispatch + de-hardcode (usage-rule, remove static unit) → T5. Canonical `start --foreground` used by service + systemd unit. Injected seams (spawn/exec_fn/terminate/is_alive/port_open/runner) → hermetic tests. All spec sections covered.

**Placeholder scan:** none — complete code/commands in every step.

**Type consistency:** `paths` constants/functions (T1) consumed by service (T2), setup (T3), doctor (T4). `service.port_open` (T2) is doctor's default (T4). `service.start(*, foreground, spawn, exec_fn, is_alive, env_path, echo)`, `stop(*, terminate, echo)`, `status(*, is_alive, port_open, echo)` consistent T2↔dispatch (T5). `setup.mcp_register`/`install_service`, `doctor.doctor` signatures consistent T3/T4↔T5. Dispatch imports `init` (3a), `service`, `setup`, `doctor`.
