# Phase 2a — Integration + always-on Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the proxy as a `systemd --user` service (always-on) and register the MCP server user-scope with a usage rule, making the council live in every project.

**Architecture:** A committed systemd unit + install/uninstall scripts (repo = source); a `consilium_mcp/server.py` fix so it runs standalone; then the controller performs the global install (service + linger + `claude mcp add` + `~/.claude/CLAUDE.md`) and a live smoke.

**Tech Stack:** systemd `--user`, bash, Python 3.10, the existing `run-proxy.sh` launcher, `claude` CLI, pytest/ruff.

## Global Constraints

- Service name `consilium-proxy`; unit installed to `~/.config/systemd/user/consilium-proxy.service`.
- The unit's `ExecStart` is `/opt/claude-projects/llm-consilium/scripts/run-proxy.sh`; `Restart=on-failure`; `WantedBy=default.target`. It reuses `run-proxy.sh` (which sources `~/.config/consilium/.env`, fails fast, execs the venv `litellm` on `127.0.0.1:4000`) — no secret/path duplicated in the unit.
- The MCP server is stdio (spawned on demand by Claude Code) — NOT a service.
- Secrets never literal in any tracked file. Commits: English, imperative, **NO `Co-Authored-By` trailer**. Stay on branch `phase-2a-integration`.
- Tools invoked as `.venv/bin/<tool>`.
- Tasks 1–2 are code (CI-testable, dispatched to subagents). Task 3 (global install + smoke) is run by the controller directly.

## File Structure

| Path | Responsibility | Task |
|---|---|---|
| `deploy/consilium-proxy.service` | systemd `--user` unit | 1 |
| `scripts/install-service.sh` | install + enable + linger (idempotent) | 1 |
| `scripts/uninstall-service.sh` | clean reversal | 1 |
| `tests/test_service_unit.py` | static checks on the unit file | 1 |
| `consilium_mcp/server.py` (modify) | repo-root `sys.path` insert (runs standalone) | 2 |
| `tests/test_mcp_server.py` (modify) | guard: insert precedes the council import | 2 |

---

### Task 1: systemd unit, static test, install/uninstall scripts

**Files:**
- Create: `deploy/consilium-proxy.service`, `scripts/install-service.sh`, `scripts/uninstall-service.sh`, `tests/test_service_unit.py`

**Interfaces:**
- Produces: the unit at `deploy/consilium-proxy.service`; `scripts/install-service.sh` (installs to `~/.config/systemd/user/`, `enable --now`, `enable-linger`, stops any manual proxy); `scripts/uninstall-service.sh`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_service_unit.py`:
```python
from pathlib import Path

UNIT = Path(__file__).resolve().parents[1] / "deploy" / "consilium-proxy.service"


def _text():
    return UNIT.read_text()


def test_execstart_points_at_run_proxy():
    text = _text()
    assert "ExecStart=" in text
    assert "scripts/run-proxy.sh" in text


def test_restart_on_failure():
    assert "Restart=on-failure" in _text()


def test_wanted_by_default_target():
    assert "WantedBy=default.target" in _text()


def test_no_secret_literal():
    text = _text()
    assert "sk-" not in text and "csk-" not in text and "gsk_" not in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_service_unit.py -q`
Expected: FAIL — `deploy/consilium-proxy.service` does not exist.

- [ ] **Step 3: Create `deploy/consilium-proxy.service`**

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

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_service_unit.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Create `scripts/install-service.sh`**

```bash
#!/usr/bin/env bash
# Install and start the Consilium proxy as a systemd --user service (always-on).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_SRC="$REPO_ROOT/deploy/consilium-proxy.service"
UNIT_DIR="$HOME/.config/systemd/user"
UNIT_DST="$UNIT_DIR/consilium-proxy.service"

if [[ ! -f "$UNIT_SRC" ]]; then
  echo "ERROR: unit file not found: $UNIT_SRC" >&2
  exit 1
fi

# Free port 4000 from any manually-started proxy before systemd takes over.
pkill -f "litellm --config" 2>/dev/null || true

mkdir -p "$UNIT_DIR"
cp "$UNIT_SRC" "$UNIT_DST"
systemctl --user daemon-reload
systemctl --user enable --now consilium-proxy.service

if loginctl enable-linger "$USER" 2>/dev/null; then
  echo "linger enabled (service survives logout/reboot)"
else
  echo "note: could not enable-linger; service runs while you are logged in"
fi

echo "--- status ---"
systemctl --user --no-pager status consilium-proxy.service | head -12 || true
```

Then: `chmod +x scripts/install-service.sh`.

- [ ] **Step 6: Create `scripts/uninstall-service.sh`**

```bash
#!/usr/bin/env bash
# Stop and remove the Consilium proxy systemd --user service.
set -euo pipefail
systemctl --user disable --now consilium-proxy.service 2>/dev/null || true
rm -f "$HOME/.config/systemd/user/consilium-proxy.service"
systemctl --user daemon-reload
echo "consilium-proxy uninstalled. (Linger unchanged: loginctl disable-linger $USER to revert.)"
```

Then: `chmod +x scripts/uninstall-service.sh`.

- [ ] **Step 7: Lint & commit**

```bash
.venv/bin/ruff check .
git add deploy/ scripts/install-service.sh scripts/uninstall-service.sh tests/test_service_unit.py
git commit -m "feat: add systemd --user unit and install/uninstall scripts for the proxy"
```
Expected: ruff `All checks passed!`.

---

### Task 2: `consilium_mcp/server.py` standalone-import fix

**Files:**
- Modify: `consilium_mcp/server.py`
- Modify: `tests/test_mcp_server.py`

**Interfaces:**
- Produces: `server.py` inserts the repo root on `sys.path` before importing `council`, so `python <repo>/consilium_mcp/server.py` resolves its imports from any cwd (mirrors `scripts/council-smoke.py`).

- [ ] **Step 1: Write the failing test**

In `tests/test_mcp_server.py`, add `from pathlib import Path` to the top-level imports (if not already present), and append:
```python
def test_server_inserts_repo_root_before_council_import():
    text = Path(server.__file__).read_text()
    insert = text.find("sys.path.insert")
    council = text.find("from council")
    assert insert != -1, "server.py must insert the repo root on sys.path"
    assert council != -1
    assert insert < council, "the sys.path insert must precede the council import"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_mcp_server.py::test_server_inserts_repo_root_before_council_import -q`
Expected: FAIL — no `sys.path.insert` in `server.py`.

- [ ] **Step 3: Edit the import block of `consilium_mcp/server.py`**

Replace the top import block:
```python
from __future__ import annotations

import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from council import orchestrator as orch
from council.types import AskResult, CouncilResult
```
with:
```python
from __future__ import annotations

import os
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from council import orchestrator as orch  # noqa: E402
from council.types import AskResult, CouncilResult  # noqa: E402
```
(The `# noqa: E402` is required because these imports follow the `sys.path` mutation — the same pattern `scripts/council-smoke.py` uses.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_mcp_server.py -q`
Expected: PASS (6 tests — the 5 existing + the new guard).

- [ ] **Step 5: Full gate**

Run: `.venv/bin/ruff check . && .venv/bin/pytest -q`
Expected: ruff `All checks passed!`; all tests green.

- [ ] **Step 6: Commit**

```bash
git add consilium_mcp/server.py tests/test_mcp_server.py
git commit -m "fix: make the MCP server resolve its imports when run standalone"
```

---

### Task 3: Global install + live smoke (controller-run)

> Run by the controller directly (the user chose "assistant runs everything"). These steps modify the global user environment; each is reversible. Not a subagent task.

- [ ] **Step 1: Install and start the service**

Run: `bash scripts/install-service.sh`
Expected: unit installed; `systemctl --user is-active consilium-proxy` → `active`; linger note printed.

- [ ] **Step 2: Verify the service-managed proxy answers**

Run (wait for liveliness, then the Phase-0 health-check with keys sourced):
```bash
curl -s --retry 30 --retry-delay 1 --retry-connrefused --max-time 5 \
  http://127.0.0.1:4000/health/liveliness -o /dev/null -w "liveliness=%{http_code}\n"
set -a; source ~/.config/consilium/.env; set +a
.venv/bin/python scripts/healthcheck.py
```
Expected: `liveliness=200`; health-check exits 0 (all providers PASS).

- [ ] **Step 3: Register the MCP server user-scope**

Run:
```bash
claude mcp add --scope user consilium -- \
  /opt/claude-projects/llm-consilium/.venv/bin/python \
  /opt/claude-projects/llm-consilium/consilium_mcp/server.py
claude mcp list
```
Expected: `claude mcp list` includes `consilium`.

- [ ] **Step 4: Create the global usage rule**

Create `~/.claude/CLAUDE.md` (it does not exist) containing the `## Free-LLM council (consilium MCP)` block from `docs/usage-rule.md` (the fenced protocol block — the tool descriptions, sensitivity semantics, and rate-limit note). Do not include the registration command in `~/.claude/CLAUDE.md` — only the usage block.

- [ ] **Step 5: Report the integration result**

Confirm to the user: service active + enabled + linger; health-check green via systemd; `consilium` registered; `~/.claude/CLAUDE.md` written; and that Claude Code must be restarted (or MCP reconnected) for the `consilium` tools to appear in an already-open session.

---

## Self-Review

**Spec coverage (against `2026-07-14-phase-2a-integration-always-on-design.md`):**
- §3 components → unit + scripts + static test (T1), server.py fix + guard (T2), global install actions (T3). ✓
- §4 unit shape (ExecStart=run-proxy.sh, Restart=on-failure, WantedBy=default.target) → T1 Step 3, asserted by `test_service_unit.py`. ✓
- §5 data flow / §2 registration fix → T2 (standalone import) + T3 (claude mcp add). ✓
- §6 error handling (fail-fast install, pkill manual proxy, linger fallback note) → T1 install script. ✓
- §7 testing (static unit test + live smoke) → T1 tests + T3 smoke. ✓
- §8 acceptance (service active/enabled/linger; standalone import; registered; ~/.claude/CLAUDE.md; ruff+pytest; manual proxy stopped) → T1/T2 gate + T3 smoke. ✓
- §9 open notes (linger privilege; restart Claude Code) → T1 linger fallback + T3 Step 5. ✓

**Placeholder scan:** No TBD/TODO; every code/config step shows full content. ✓

**Type consistency:** `consilium-proxy.service` name, `ExecStart=…/scripts/run-proxy.sh`, and the `sys.path.insert(...parents[1])` pattern match across the unit, install script, `test_service_unit.py`, and `server.py`/its guard test. The registration command in T3 matches `docs/usage-rule.md`. ✓
