# Phase 3b — Runtime CLI (start/stop/status/mcp-register/install-service/doctor) design/spec

> Status: approved for planning (2026-07-14). Next: writing-plans.
> Second sub-wave of Phase 3 (distribution), after 3a (init wizard). Then 3c = README/LICENSE/public.

## Business context

3a lets a colleague set up keys; 3b lets them *run* consilium and wire it into Claude Code
with one CLI — cross-platform (Linux + Windows), no bash. The proxy is managed by
`consilium start/stop/status` (backgrounded process + PID file), the MCP is registered by
`consilium mcp-register` (absolute paths, so it works from any project — the #12 hotfix
proved why relative paths break), optional Linux autostart via `consilium install-service`,
and `consilium doctor` diagnoses the whole setup. This removes the remaining hardcoded
`/opt/...` paths so the repo runs wherever it's cloned.

## Goal

Extend the `consilium` package with `start`, `stop`, `status`, `mcp-register`,
`install-service`, and `doctor` subcommands (`python -m consilium <cmd>`), all
cross-platform and path-agnostic (paths derived from the module location), and de-hardcode
the remaining `/opt` references.

## Global Constraints (verbatim, apply to every task)

- **Cross-platform:** stdlib + httpx only; POSIX and Windows both supported. No bash in the
  runtime path. Guard OS-specific calls (`os.name`/`sys.platform`).
- **Path-agnostic:** every path derives from the module location (`Path(__file__)`), never
  a hardcoded `/opt/...` or the CWD. The single source of truth is `consilium/paths.py`.
- **Secrets:** `start` loads `~/.config/consilium/.env` into the proxy subprocess env; it
  never prints key values or writes them anywhere new.
- **Canonical launcher:** `consilium start --foreground` (loads `.env`, execs `litellm`) is
  the single source of truth; `consilium start` (background) and the generated systemd unit
  both invoke it. The existing `run-proxy.sh` stays as a Linux-legacy alias (not removed).
- **Testable:** process spawning, signals, sockets, and subprocess command runners are
  injected (dependency injection) so tests are hermetic — no real proxy, no real network,
  no real `claude`/`systemctl` calls. Pure command/template builders are unit-tested by
  their output.
- **Idempotent & non-destructive:** re-running any command is safe; `mcp-register` is
  remove-then-add; `install-service` overwrites its own unit only. This task does NOT
  force-replace the currently-running deployed systemd unit on this machine.
- Add any new `consilium` submodules under the existing `known-first-party`. Python 3.10+;
  `ruff check .` clean + `pytest -q` green. Commits English imperative, no `Co-Authored-By`.
  Branch `phase-3b-runtime`.

## 1. Shared paths — `consilium/paths.py`

Single source of truth for locations, all derived from the module or `$HOME`:

- `REPO_ROOT = Path(__file__).resolve().parents[1]`
- `CONFIG_PATH = REPO_ROOT / "proxy" / "config.yaml"`
- `SERVER_PATH = REPO_ROOT / "consilium_mcp" / "server.py"`
- `CONFIG_DIR = Path.home() / ".config" / "consilium"`; `PID_PATH = CONFIG_DIR / "proxy.pid"`;
  `LOG_PATH = CONFIG_DIR / "proxy.log"`
- `PROXY_HOST = "127.0.0.1"`, `PROXY_PORT = 4000`
- `venv_python() -> Path` = `Path(sys.executable)` (the interpreter running us — in the venv)
- `litellm_exe() -> Path` = `Path(sys.executable).parent / ("litellm.exe" if os.name=="nt" else "litellm")`

## 2. Proxy lifecycle — `consilium/service.py`

- `proxy_command() -> list[str]` = `[str(litellm_exe()), "--config", str(CONFIG_PATH),
  "--host", PROXY_HOST, "--port", str(PROXY_PORT)]` (pure).
- `proxy_env(env_path=DEFAULT_ENV_PATH) -> dict` = `os.environ` merged with
  `env_file.load(env_path)` (provider keys + master key into the subprocess env).
- `start(*, foreground=False, spawn=subprocess.Popen, is_alive=..., env_path=...) -> int`:
  - `foreground=True`: run `proxy_command()` with `proxy_env()` and block (POSIX: `os.execvpe`
    so systemd tracks litellm directly; the injected `spawn` is not used here — see plan for
    a testable seam). Returns the child's return code.
  - `foreground=False`: if a live PID exists → "already running", return 0; else spawn
    detached (POSIX `start_new_session=True`; Windows `DETACHED_PROCESS |
    CREATE_NEW_PROCESS_GROUP`), stdout/stderr → `LOG_PATH`, write the PID to `PID_PATH`,
    print "started (pid …)", return 0.
- `stop(*, terminate=..., ) -> int`: read `PID_PATH`; none → "not running", 0; else
  `terminate(pid)` (POSIX `os.kill(pid, SIGTERM)`; Windows `taskkill /PID <pid> /F`), remove
  the PID file, return 0.
- `status(*, is_alive=..., port_open=...) -> int`: report PID-alive (from `PID_PATH`) and
  whether `PROXY_HOST:PROXY_PORT` accepts a connection; return 0.
- Default helpers (injectable, overridden in tests): `_is_alive(pid)` (POSIX `os.kill(pid,0)`;
  Windows `tasklist` check), `_port_open(host, port)` (`socket.create_connection`, 1s timeout),
  `_terminate(pid)`, `_read_pid()`/`_write_pid()`.

## 3. Wiring commands — `consilium/setup.py`

- `mcp_add_command() -> list[str]` = `["claude","mcp","add","--scope","user","consilium","--",
  str(venv_python()), str(SERVER_PATH)]` (pure, absolute paths).
- `mcp_remove_command() -> list[str]` = `["claude","mcp","remove","--scope","user","consilium"]`.
- `mcp_register(*, runner=subprocess.run) -> int`: run remove (ignore failure — may be
  absent), then add; report success/failure. Idempotent.
- `systemd_unit_text(python: str, repo_root: str) -> str` (pure): a `Type=simple` `--user`
  unit with `WorkingDirectory=<repo_root>`, `Environment=PYTHONPATH=<repo_root>`,
  `ExecStart=<python> -m consilium start --foreground`, `Restart=on-failure`,
  `WantedBy=default.target`.
- `install_service(*, runner=subprocess.run) -> int`: non-Linux → print Task-Scheduler
  guidance and return 0; Linux → write the unit to `~/.config/systemd/user/consilium-proxy.service`,
  `systemctl --user daemon-reload`, `enable --now consilium-proxy`, `loginctl enable-linger`.

## 4. Diagnostics — `consilium/doctor.py`

- `doctor(*, port_open=..., runner=subprocess.run, env_path=...) -> int`: prints a table:
  - **Keys:** per `PROVIDERS`, 🟢 if all its env vars are present in `.env`, else ⚪ dormant.
  - **Proxy:** 🟢/🔴 whether `PROXY_HOST:PROXY_PORT` is reachable.
  - **MCP:** 🟢/🔴 whether `claude mcp list` output contains `consilium` (via `runner`).
  Returns 0 (diagnostic, never fatal). Optional `--ping` reuses 3a `init.live_ping` (future;
  local checks by default).

## 5. Entrypoint — `consilium/__main__.py`

Extend the dispatch: `init` (3a), `start` (with `--foreground` flag), `stop`, `status`,
`mcp-register`, `install-service`, `doctor`; unknown/absent → a usage message listing all
commands, return 2.

## 6. De-hardcode remaining `/opt` paths

- `docs/usage-rule.md`: replace the hardcoded `claude mcp add … /opt/claude-projects/…`
  block with `python -m consilium mcp-register` (paths derived automatically).
- `deploy/consilium-proxy.service`: superseded by `consilium install-service` (which
  generates a path-correct unit). Remove the hardcoded static file (it is a template, not
  the installed unit; the running deployment on this machine is untouched).
- `run-proxy.sh` already resolves `REPO_ROOT` dynamically — left as the Linux-legacy alias.

## 7. Testing

- **paths**: `REPO_ROOT`/`CONFIG_PATH`/`SERVER_PATH` absolute and point at real files;
  `litellm_exe()` sits beside `venv_python()`; `.exe` suffix only on `nt`.
- **service**: `proxy_command()` shape; `proxy_env` merges `.env` over `os.environ` (keys
  present); `start(background)` with an injected `spawn` fake → writes the PID, "already
  running" when a live PID exists (injected `is_alive`); `stop` calls the injected
  `terminate` with the PID and clears the file, "not running" when no PID; `status` reflects
  injected `is_alive`/`port_open`. No real process spawned.
- **setup**: `mcp_add_command`/`mcp_remove_command` carry absolute venv-python + server
  paths; `mcp_register` calls remove-then-add via an injected runner; `systemd_unit_text`
  contains `ExecStart=… -m consilium start --foreground`, the repo `WorkingDirectory`, and
  `PYTHONPATH`; `install_service` on non-Linux prints guidance and does not shell out.
- **doctor**: with a `tmp` `.env` (some keys) + injected `port_open`/`runner`, the table
  reflects present/dormant keys, proxy up/down, and mcp registered/not.
- **entrypoint**: each subcommand dispatches to the right function (inject/monkeypatch the
  target); unknown command → usage + rc 2.

## 8. Out of scope (explicit)

- README / LICENSE / making the repo public → **3c**.
- Removing `run-proxy.sh` or force-migrating the running systemd unit on this machine.
- A live `doctor --ping` (local checks only for now; the hook is noted).
- Windows Task Scheduler *automation* (we print guidance; no programmatic scheduled task).

## 9. Files

- `consilium/paths.py`, `consilium/service.py`, `consilium/setup.py`, `consilium/doctor.py` — NEW.
- `consilium/__main__.py` — extend dispatch.
- `docs/usage-rule.md` — `mcp-register` instead of the hardcoded command.
- `deploy/consilium-proxy.service` — removed (superseded by generated unit).
- Tests: `tests/test_paths.py`, `tests/test_service.py`, `tests/test_setup.py`,
  `tests/test_doctor.py`, and `tests/test_cli_main.py` (dispatch) — NEW/extended.
