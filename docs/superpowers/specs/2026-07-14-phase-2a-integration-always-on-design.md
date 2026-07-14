# Phase 2a — Integration + always-on

**Date:** 2026-07-14
**Status:** Design approved — pending written-spec review, then `writing-plans`.
**Builds on:** Phase 1 (council engine + `consilium_mcp` server) on `main`.
**Phase map:** see Phase 1 spec §14. Phase 2 = deployment hardening; 2a is its first sub-project.

## 1. Goal & scope

Make the council **always-on and discoverable**: the proxy runs as a `systemd --user`
service (survives logout/reboot), the MCP server is registered user-scope (available in
every project), and a usage rule in `~/.claude/CLAUDE.md` tells Claude when to consult it.
This is the "integrate" step — it turns the Phase-0/1 code into a live daily-use tool.

**In scope:** systemd unit + install/uninstall scripts, a `consilium_mcp/server.py`
fix so it runs standalone, running the global install (service + linger + MCP
registration + `~/.claude/CLAUDE.md`), and a smoke verification.
**Out of scope (later Phase-2 sub-projects):** backoff / RPD telemetry / rotation (2b),
additional providers (2c), a shell `council` CLI, running the MCP server itself as a
service (it is stdio, spawned on demand by Claude Code).

## 2. Decisions locked this session

- **Runtime:** the proxy becomes a `systemd --user` service; `loginctl enable-linger`
  so it survives logout/reboot. The MCP server stays stdio (Claude Code spawns it).
- **Install ownership:** the assistant creates the repo artifacts AND runs the global
  install steps (service, linger, `claude mcp add`, `~/.claude/CLAUDE.md`), with an
  uninstall script for reversal.
- **Registration fix:** `consilium_mcp/server.py` inserts the repo root on `sys.path`
  (mirroring `scripts/council-smoke.py`) so `python consilium_mcp/server.py` resolves
  `import council` regardless of cwd — required for the MCP registration to work.

## 3. Components (repo = source; installed artifacts = global)

| Path | Responsibility |
|---|---|
| `deploy/consilium-proxy.service` | `systemd --user` unit: runs `scripts/run-proxy.sh`, `Restart=on-failure`, `WantedBy=default.target` |
| `scripts/install-service.sh` | stop any manual proxy → install unit to `~/.config/systemd/user/` → `daemon-reload` → `enable --now` → `enable-linger` → print status (idempotent) |
| `scripts/uninstall-service.sh` | `disable --now` + remove unit + `daemon-reload` (clean reversal) |
| `consilium_mcp/server.py` (modify) | add repo-root `sys.path` insert so the server runs standalone |
| `tests/test_service_unit.py` | static CI-safe checks on the unit file (ExecStart → launcher, Restart, WantedBy, no secret literal) |

**Global install actions the assistant performs (not committed — deployment side):**
1. `bash scripts/install-service.sh`.
2. `claude mcp add --scope user consilium -- <repo>/.venv/bin/python <repo>/consilium_mcp/server.py`.
3. Create `~/.claude/CLAUDE.md` (it does not exist) with the usage block from
   `docs/usage-rule.md`.

## 4. The systemd unit (shape)

```ini
[Unit]
Description=Consilium LiteLLM proxy (free-LLM council compute layer)

[Service]
Type=simple
ExecStart=/opt/claude-projects/llm-consilium/scripts/run-proxy.sh
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

`run-proxy.sh` already sources `~/.config/consilium/.env`, fails fast on a missing var,
and execs the venv `litellm` on `127.0.0.1:4000` — the unit reuses that tested launcher,
so no secret or path is duplicated in the unit. No `network-online.target` dependency:
the proxy binds loopback (always up) and only makes outbound calls per request.

## 5. Data flow

Boot / login → `systemd --user` starts `consilium-proxy` → proxy on `127.0.0.1:4000`.
Any Claude Code project → the registered `consilium` MCP server (stdio, spawned on
demand) → orchestrator → proxy → free providers. The `~/.claude/CLAUDE.md` rule tells
Claude when to reach for `ask`/`council`.

## 6. Error handling

- Service: `Restart=on-failure` / `RestartSec=5` — a crash restarts automatically.
- `install-service.sh`: fails clearly if the unit source is missing; `pkill` the manual
  proxy before enabling to avoid a port conflict; if `enable-linger` needs privileges it
  can't get, it warns but the service still runs while logged in.
- `enable-linger` and MCP registration are reversible (uninstall script; `claude mcp
  remove consilium`).

## 7. Testing & verification

- **CI-safe:** `tests/test_service_unit.py` validates the unit's ExecStart points at
  `scripts/run-proxy.sh`, `Restart=on-failure`, `WantedBy=default.target`, and that no
  secret literal appears. `ruff` + `pytest` stay green.
- **Live smoke (assistant runs after install):**
  - `systemctl --user is-active consilium-proxy` → `active`.
  - the Phase-0 live health-check passes against the systemd-managed proxy.
  - `claude mcp list` shows `consilium`.
  - `~/.claude/CLAUDE.md` contains the usage block.

## 8. Acceptance criteria

- The proxy runs under `systemd --user`, is enabled, and linger is on (survives logout).
- `python consilium_mcp/server.py` imports cleanly (repo-root on path); `claude mcp add`
  registers `consilium` and it appears in `claude mcp list`.
- `~/.claude/CLAUDE.md` exists and carries the usage protocol block.
- `ruff` clean + `pytest` green (incl. the new unit-file test); the manual nohup proxy is
  stopped (systemd owns port 4000).
- No secret in any tracked file or the unit.

## 9. Open notes (non-blocking)

- `enable-linger` for the current user usually needs no sudo; if the environment blocks
  it, the service still runs during an active session and the note is surfaced.
- Restarting Claude Code (or reconnecting MCP) is required for the newly-registered
  `consilium` tools to appear in an already-open session — noted in the install output.
