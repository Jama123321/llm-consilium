# Phase 0 MVP — LiteLLM Proxy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up a self-hosted LiteLLM proxy on `127.0.0.1:4000` fronting 3 Tier-A providers (Cerebras, Groq, Cloudflare) with a live per-provider health-check.

**Architecture:** One OpenAI-compatible `/v1` (LiteLLM proxy) reads a declarative `proxy/config.yaml` where every alias references credentials via `os.environ/*` (loaded from `~/.config/consilium/.env`) and carries a `model_info.privacy_tier: A` tag. A launch script validates env then runs the proxy; a Python health-check probes `/v1/models` plus a 1-token completion per provider. Tests are CI-safe (no live keys): config-shape checks + health-check logic with `httpx` mocked.

**Tech Stack:** Python 3.10 + repo-local `.venv`, LiteLLM (`[proxy]`), httpx, PyYAML, pytest, ruff. Bash launcher.

## Global Constraints

- **Python 3.10** runtime; repo-local `./.venv/` (gitignored). Tooling invoked as `.venv/bin/<tool>`.
- **Tier-A only.** No Tier-B provider/endpoint anywhere in Phase 0.
- **Secrets never literal** in code/config/logs/git. Config references only `os.environ/*`. Real keys live only in `~/.config/consilium/.env` (chmod 600).
- **Proxy binds `127.0.0.1` only.** Master key via `LITELLM_MASTER_KEY`.
- **No DB/UI** — stateless, config-only proxy.
- **Every alias carries `model_info.privacy_tier: A`.**
- The 5 aliases are exactly: `council/cerebras-qwen-235b`, `council/cerebras-llama-70b`, `council/groq-llama-70b`, `council/groq-gpt-oss-120b`, `council/cloudflare-llama-70b`.
- Commits: English, imperative, **no `Co-Authored-By` trailer**. Never `--no-verify` / force-push. Work stays on branch `phase-0-mvp-proxy`; do not merge to `main` without explicit user OK.
- Exact model ids are provisional (audit warns ids drift) — the live smoke run pins them; a mismatch shows up as a health-check FAIL, fixed by editing `config.yaml`.

## File Structure

| Path | Responsibility | Task |
|---|---|---|
| `requirements.txt` | Pinned dependency set | 1 |
| `pyproject.toml` | ruff + pytest config | 1 |
| `CLAUDE.md` (edit) | Wording `Python 3.11+` → `Python 3.10+` | 1 |
| `proxy/config.yaml` | Declarative Tier-A provider registry | 2 |
| `tests/test_config.py` | Config-shape assertions | 2 |
| `.env.example` | Secrets contract (placeholders + provisioning notes) | 3 |
| `scripts/run-proxy.sh` | Load env, fail-fast, launch proxy | 3 |
| `tests/test_run_proxy.py` | Env-validation + `.env.example` consistency | 3 |
| `scripts/healthcheck.py` | Live `/v1/models` + per-provider completion probe | 4 |
| `tests/test_healthcheck.py` | Probe classification + aggregation (httpx mocked) | 4 |
| `proxy/README.md` | Run + live-smoke instructions | 5 |

---

### Task 1: Toolchain, dependencies, venv, CLAUDE.md wording

**Files:**
- Create: `requirements.txt`
- Create: `pyproject.toml`
- Modify: `CLAUDE.md` (Stack line)

**Interfaces:**
- Consumes: nothing.
- Produces: a working `./.venv/` with `ruff`, `pytest`, `litellm`, `httpx`, `yaml` importable; ruff/pytest config (`testpaths=["tests"]`, `pythonpath=["scripts"]`, `known-first-party=["healthcheck"]`).

- [ ] **Step 1: Create `requirements.txt`**

```
# Consilium Phase 0 — pinned dependency set (bounded ranges: installable + stable).
litellm[proxy]>=1.50,<2
httpx>=0.27,<1
pyyaml>=6,<7
pytest>=8,<9
ruff>=0.6
```

- [ ] **Step 2: Create `pyproject.toml`**

```toml
[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]

[tool.ruff.lint.isort]
known-first-party = ["healthcheck"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["scripts"]
```

- [ ] **Step 3: Create the venv and install**

Run:
```bash
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```
Expected: installs succeed (litellm[proxy] is large — allow a few minutes). Confirm with `.venv/bin/python -c "import litellm, httpx, yaml; print('ok')"` → prints `ok`.

- [ ] **Step 4: Edit `CLAUDE.md` wording**

Find:
```
- **Python 3.11+** (LiteLLM + MCP are Python-native), `asyncio`/`httpx` for the
```
Replace with:
```
- **Python 3.10+** (LiteLLM + MCP are Python-native), `asyncio`/`httpx` for the
```

- [ ] **Step 5: Verify ruff runs clean**

Run: `.venv/bin/ruff check .`
Expected: `All checks passed!` (no Python files yet), exit 0.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt pyproject.toml CLAUDE.md
git commit -m "chore: add Phase 0 toolchain, pinned deps, and 3.10 runtime note"
```

---

### Task 2: `proxy/config.yaml` — Tier-A provider registry

**Files:**
- Create: `tests/test_config.py`
- Create: `proxy/config.yaml`

**Interfaces:**
- Consumes: the toolchain from Task 1 (`yaml`, `pytest`).
- Produces: the 5 canonical aliases and the `model_info.privacy_tier` tag convention consumed by later phases; `general_settings.master_key: os.environ/LITELLM_MASTER_KEY`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_config.py`:
```python
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).resolve().parents[1] / "proxy" / "config.yaml"
EXPECTED_ALIASES = {
    "council/cerebras-qwen-235b",
    "council/cerebras-llama-70b",
    "council/groq-llama-70b",
    "council/groq-gpt-oss-120b",
    "council/cloudflare-llama-70b",
}


def _load():
    return yaml.safe_load(CONFIG_PATH.read_text())


def test_expected_aliases_present():
    cfg = _load()
    names = {m["model_name"] for m in cfg["model_list"]}
    assert names == EXPECTED_ALIASES


def test_every_alias_tagged_tier_a():
    cfg = _load()
    for m in cfg["model_list"]:
        assert m["model_info"]["privacy_tier"] == "A", m["model_name"]


def test_no_literal_secrets():
    cfg = _load()
    for m in cfg["model_list"]:
        params = m["litellm_params"]
        assert params["api_key"].startswith("os.environ/"), m["model_name"]
        if "api_base" in params:
            assert params["api_base"].startswith("os.environ/"), m["model_name"]


def test_master_key_via_env():
    cfg = _load()
    assert cfg["general_settings"]["master_key"] == "os.environ/LITELLM_MASTER_KEY"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_config.py -q`
Expected: FAIL — `proxy/config.yaml` does not exist (FileNotFoundError).

- [ ] **Step 3: Create `proxy/config.yaml`**

```yaml
# Consilium LiteLLM proxy — Phase 0 (Tier-A providers only).
# Secrets are referenced via os.environ/* and loaded from ~/.config/consilium/.env.
# The privacy_tier tags are read by the Phase 1 council privacy gate.
model_list:
  - model_name: council/cerebras-qwen-235b
    litellm_params:
      model: cerebras/qwen-3-235b
      api_key: os.environ/CEREBRAS_API_KEY
      rpm: 5
    model_info:
      privacy_tier: A
  - model_name: council/cerebras-llama-70b
    litellm_params:
      model: cerebras/llama-3.3-70b
      api_key: os.environ/CEREBRAS_API_KEY
      rpm: 5
    model_info:
      privacy_tier: A
  - model_name: council/groq-llama-70b
    litellm_params:
      model: groq/llama-3.3-70b-versatile
      api_key: os.environ/GROQ_API_KEY
      rpm: 30
    model_info:
      privacy_tier: A
  # Groq free tier: does NOT train on prompts (the Tier-A criterion); default keeps
  # 7-day operational logs — full zero-retention needs ZDR (later action, non-blocking).
  - model_name: council/groq-gpt-oss-120b
    litellm_params:
      model: groq/openai/gpt-oss-120b
      api_key: os.environ/GROQ_API_KEY
      rpm: 30
    model_info:
      privacy_tier: A
  - model_name: council/cloudflare-llama-70b
    litellm_params:
      model: openai/@cf/meta/llama-3.3-70b-instruct-fp8-fast
      api_base: os.environ/CLOUDFLARE_API_BASE
      api_key: os.environ/CLOUDFLARE_API_TOKEN
    model_info:
      privacy_tier: A
router_settings:
  num_retries: 1
general_settings:
  master_key: os.environ/LITELLM_MASTER_KEY
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_config.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Lint**

Run: `.venv/bin/ruff check .`
Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add proxy/config.yaml tests/test_config.py
git commit -m "feat: add Tier-A LiteLLM proxy config with privacy_tier tags"
```

---

### Task 3: `.env.example` + `scripts/run-proxy.sh` — env contract & launcher

**Files:**
- Create: `.env.example`
- Create: `scripts/run-proxy.sh`
- Create: `tests/test_run_proxy.py`

**Interfaces:**
- Consumes: `proxy/config.yaml` (the launcher points litellm at it).
- Produces: the required env-var set `{CEREBRAS_API_KEY, GROQ_API_KEY, CLOUDFLARE_API_TOKEN, CLOUDFLARE_API_BASE, LITELLM_MASTER_KEY}`; launcher honors `CONSILIUM_ENV_FILE` (override secrets path) and `CONSILIUM_CHECK_ONLY` (validate env then exit 0 without launching).

- [ ] **Step 1: Write the failing test**

Create `tests/test_run_proxy.py`:
```python
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run-proxy.sh"
ENV_EXAMPLE = ROOT / ".env.example"
REQUIRED_VARS = {
    "CEREBRAS_API_KEY",
    "GROQ_API_KEY",
    "CLOUDFLARE_API_TOKEN",
    "CLOUDFLARE_API_BASE",
    "LITELLM_MASTER_KEY",
}


def _run(env):
    full = {"PATH": os.environ["PATH"], "CONSILIUM_ENV_FILE": "/nonexistent"}
    full.update(env)
    return subprocess.run(
        ["bash", str(SCRIPT)], env=full, capture_output=True, text=True
    )


def _all_vars():
    return {v: "x" for v in REQUIRED_VARS}


def test_check_only_passes_with_all_vars():
    env = _all_vars()
    env["CONSILIUM_CHECK_ONLY"] = "1"
    result = _run(env)
    assert result.returncode == 0, result.stderr


def test_missing_var_fails_fast():
    env = _all_vars()
    del env["CLOUDFLARE_API_BASE"]
    env["CONSILIUM_CHECK_ONLY"] = "1"
    result = _run(env)
    assert result.returncode != 0
    assert "CLOUDFLARE_API_BASE" in result.stderr


def test_env_example_covers_required_vars():
    keys = {
        line.split("=", 1)[0].strip()
        for line in ENV_EXAMPLE.read_text().splitlines()
        if "=" in line and not line.strip().startswith("#")
    }
    assert REQUIRED_VARS <= keys
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_run_proxy.py -q`
Expected: FAIL — script and `.env.example` do not exist.

- [ ] **Step 3: Create `.env.example`**

```bash
# Consilium secrets — copy to ~/.config/consilium/.env (chmod 600).
# NEVER commit real values. All are free / no credit card.

# Cerebras — cloud.cerebras.ai -> API Keys (1M tokens/day)
CEREBRAS_API_KEY=csk-REPLACE_ME

# Groq — console.groq.com -> API Keys
GROQ_API_KEY=gsk_REPLACE_ME

# Cloudflare Workers AI — dash.cloudflare.com -> My Profile -> API Tokens
#   -> Create Token -> "Workers AI" template
CLOUDFLARE_API_TOKEN=REPLACE_ME

# Full OpenAI-compat base with YOUR account id (Cloudflare dashboard sidebar)
CLOUDFLARE_API_BASE=https://api.cloudflare.com/client/v4/accounts/YOUR_ACCOUNT_ID/ai/v1

# Proxy auth — self-generated, e.g.  printf 'sk-%s' "$(openssl rand -hex 24)"
LITELLM_MASTER_KEY=sk-REPLACE_ME
```

- [ ] **Step 4: Create `scripts/run-proxy.sh`**

```bash
#!/usr/bin/env bash
# Load Consilium secrets, validate them, and launch the LiteLLM proxy on localhost.
set -euo pipefail

ENV_FILE="${CONSILIUM_ENV_FILE:-$HOME/.config/consilium/.env}"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

required=(CEREBRAS_API_KEY GROQ_API_KEY CLOUDFLARE_API_TOKEN CLOUDFLARE_API_BASE LITELLM_MASTER_KEY)
missing=()
for var in "${required[@]}"; do
  if [[ -z "${!var:-}" ]]; then
    missing+=("$var")
  fi
done
if (( ${#missing[@]} > 0 )); then
  echo "ERROR: missing required env vars: ${missing[*]}" >&2
  exit 1
fi

if [[ -n "${CONSILIUM_CHECK_ONLY:-}" ]]; then
  echo "OK: all required env vars present (check-only, not launching)"
  exit 0
fi

CONFIG="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/proxy/config.yaml"
exec litellm --config "$CONFIG" --host 127.0.0.1 --port 4000
```

Then make it executable:
```bash
chmod +x scripts/run-proxy.sh
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_run_proxy.py -q`
Expected: PASS (3 tests).

- [ ] **Step 6: Lint**

Run: `.venv/bin/ruff check .`
Expected: `All checks passed!`

- [ ] **Step 7: Commit**

```bash
git add .env.example scripts/run-proxy.sh tests/test_run_proxy.py
git commit -m "feat: add secrets contract and env-validating proxy launcher"
```

---

### Task 4: `scripts/healthcheck.py` — live per-provider probe

**Files:**
- Create: `scripts/healthcheck.py`
- Create: `tests/test_healthcheck.py`

**Interfaces:**
- Consumes: a running proxy at `CONSILIUM_BASE_URL` (default `http://127.0.0.1:4000/v1`), auth via `LITELLM_MASTER_KEY`; alias names from Task 2.
- Produces: `ProbeResult(name, ok, detail)`; pure functions `check_models(returned, expected)`, `classify_completion(name, status_code, error)`, `summarize(results) -> int`; I/O helpers `_probe_models(client)`, `_probe_completion(client, name, alias)`; `run_probes(base_url, api_key)`; `main() -> int`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_healthcheck.py`:
```python
import httpx

import healthcheck as hc


def test_check_models_all_present():
    assert hc.check_models(set(hc.EXPECTED_ALIASES), hc.EXPECTED_ALIASES).ok


def test_check_models_reports_missing():
    partial = set(hc.EXPECTED_ALIASES) - {"council/groq-llama-70b"}
    result = hc.check_models(partial, hc.EXPECTED_ALIASES)
    assert not result.ok
    assert "council/groq-llama-70b" in result.detail


def test_classify_completion_ok():
    assert hc.classify_completion("groq", 200, None).ok


def test_classify_completion_401():
    result = hc.classify_completion("groq", 401, None)
    assert not result.ok and "401" in result.detail


def test_classify_completion_429():
    result = hc.classify_completion("groq", 429, None)
    assert not result.ok and "429" in result.detail


def test_classify_completion_transport_error():
    result = hc.classify_completion("groq", None, "timeout")
    assert not result.ok and result.detail == "timeout"


def test_summarize_exit_codes():
    assert hc.summarize([hc.ProbeResult("a", True, "x")]) == 0
    mixed = [hc.ProbeResult("a", True, "x"), hc.ProbeResult("b", False, "y")]
    assert hc.summarize(mixed) == 1


def test_probe_models_with_mock_transport():
    def handler(request):
        return httpx.Response(200, json={"data": [{"id": a} for a in hc.EXPECTED_ALIASES]})

    client = httpx.Client(base_url="http://test/v1", transport=httpx.MockTransport(handler))
    assert hc._probe_models(client).ok


def test_probe_completion_with_mock_transport():
    def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    client = httpx.Client(base_url="http://test/v1", transport=httpx.MockTransport(handler))
    assert hc._probe_completion(client, "groq", "council/groq-llama-70b").ok
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_healthcheck.py -q`
Expected: FAIL — `healthcheck` module not found.

- [ ] **Step 3: Create `scripts/healthcheck.py`**

```python
#!/usr/bin/env python3
"""Live health-check for the Consilium LiteLLM proxy.

Probes GET /v1/models and sends a 1-token completion to one alias per Tier-A
provider. Prints per-probe PASS/FAIL and exits non-zero if any probe fails.
Reads no secret except the proxy master key (LITELLM_MASTER_KEY).
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass

import httpx

DEFAULT_BASE_URL = "http://127.0.0.1:4000/v1"
REQUEST_TIMEOUT = 30.0

EXPECTED_ALIASES = (
    "council/cerebras-qwen-235b",
    "council/cerebras-llama-70b",
    "council/groq-llama-70b",
    "council/groq-gpt-oss-120b",
    "council/cloudflare-llama-70b",
)

# One representative alias per provider (proves that key + route work end-to-end).
PROVIDER_PROBES = {
    "cerebras": "council/cerebras-qwen-235b",
    "groq": "council/groq-llama-70b",
    "cloudflare": "council/cloudflare-llama-70b",
}


@dataclass(frozen=True)
class ProbeResult:
    name: str
    ok: bool
    detail: str


def check_models(returned: set[str], expected: tuple[str, ...]) -> ProbeResult:
    missing = [a for a in expected if a not in returned]
    if missing:
        return ProbeResult("models", False, f"missing aliases: {', '.join(missing)}")
    return ProbeResult("models", True, f"{len(expected)} aliases present")


def classify_completion(name: str, status_code: int | None, error: str | None) -> ProbeResult:
    if error is not None:
        return ProbeResult(name, False, error)
    if status_code == 200:
        return ProbeResult(name, True, "completion ok")
    if status_code == 401:
        return ProbeResult(name, False, "401 auth failed (check API key)")
    if status_code == 429:
        return ProbeResult(name, False, "429 rate-limited")
    return ProbeResult(name, False, f"HTTP {status_code}")


def summarize(results: list[ProbeResult]) -> int:
    all_ok = True
    for r in results:
        print(f"[{'PASS' if r.ok else 'FAIL'}] {r.name}: {r.detail}")
        all_ok = all_ok and r.ok
    print("---")
    print("OK: all probes passed" if all_ok else "FAILED: one or more probes failed")
    return 0 if all_ok else 1


def _probe_models(client: httpx.Client) -> ProbeResult:
    try:
        resp = client.get("/models")
    except httpx.HTTPError as exc:
        return ProbeResult("models", False, f"request error: {exc.__class__.__name__}")
    if resp.status_code != 200:
        return ProbeResult("models", False, f"HTTP {resp.status_code}")
    returned = {m.get("id") for m in resp.json().get("data", [])}
    return check_models(returned, EXPECTED_ALIASES)


def _probe_completion(client: httpx.Client, name: str, alias: str) -> ProbeResult:
    payload = {
        "model": alias,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
    }
    try:
        resp = client.post("/chat/completions", json=payload)
    except httpx.TimeoutException:
        return classify_completion(name, None, "timeout")
    except httpx.HTTPError as exc:
        return classify_completion(name, None, f"request error: {exc.__class__.__name__}")
    return classify_completion(name, resp.status_code, None)


def run_probes(base_url: str, api_key: str) -> list[ProbeResult]:
    headers = {"Authorization": f"Bearer {api_key}"}
    with httpx.Client(base_url=base_url, headers=headers, timeout=REQUEST_TIMEOUT) as client:
        results = [_probe_models(client)]
        for name, alias in PROVIDER_PROBES.items():
            results.append(_probe_completion(client, name, alias))
    return results


def main() -> int:
    base_url = os.environ.get("CONSILIUM_BASE_URL", DEFAULT_BASE_URL)
    api_key = os.environ.get("LITELLM_MASTER_KEY", "")
    if not api_key:
        print("ERROR: LITELLM_MASTER_KEY not set", file=sys.stderr)
        return 2
    return summarize(run_probes(base_url, api_key))


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_healthcheck.py -q`
Expected: PASS (9 tests).

- [ ] **Step 5: Lint**

Run: `.venv/bin/ruff check .`
Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add scripts/healthcheck.py tests/test_healthcheck.py
git commit -m "feat: add live per-provider proxy health-check"
```

---

### Task 5: `proxy/README.md` run + live-smoke docs, and final gate

**Files:**
- Create: `proxy/README.md`

**Interfaces:**
- Consumes: everything above.
- Produces: operator docs; final green gate on the whole branch.

- [ ] **Step 1: Create `proxy/README.md`**

````markdown
# Consilium proxy (Phase 0)

Single OpenAI-compatible `/v1` on `127.0.0.1:4000` fronting 3 Tier-A providers.

## 1. Provision keys (once)
Copy the contract and fill real values (all free, no card):
```bash
mkdir -p ~/.config/consilium
cp .env.example ~/.config/consilium/.env
chmod 600 ~/.config/consilium/.env
# edit ~/.config/consilium/.env — see the comments for each console
```

## 2. Run the proxy
```bash
bash scripts/run-proxy.sh          # loads the env file, validates, launches on 127.0.0.1:4000
```
List the registered aliases:
```bash
curl -s -H "Authorization: Bearer $LITELLM_MASTER_KEY" http://127.0.0.1:4000/v1/models
```

## 3. Live health-check (in a second shell)
```bash
set -a; source ~/.config/consilium/.env; set +a
.venv/bin/python scripts/healthcheck.py
```
Prints `[PASS]/[FAIL]` for `/v1/models` and one completion per provider; exits 0 only if all pass. A model-id mismatch shows as a FAIL — fix the id in `proxy/config.yaml`.
````

- [ ] **Step 2: Run the full CI-safe gate**

Run: `.venv/bin/ruff check . && .venv/bin/pytest -q`
Expected: ruff `All checks passed!`; pytest all green (16 tests: 4 config + 3 run-proxy + 9 healthcheck).

- [ ] **Step 3: Commit**

```bash
git add proxy/README.md
git commit -m "docs: add proxy run and live health-check instructions"
```

---

## Self-Review

**Spec coverage (against `2026-07-13-phase-0-mvp-proxy-design.md`):**
- §3 components → all 7 present across Tasks 1-5. ✓
- §4 five curated aliases → Task 2 config + asserted in `test_config.py` and `EXPECTED_ALIASES`. ✓
- §5 LiteLLM wiring (native prefixes, CF openai-shim via `CLOUDFLARE_API_BASE`, `privacy_tier` tag, `num_retries: 1`, master_key) → Task 2. ✓
- §6 secrets contract → `.env.example` (Task 3), referenced only via `os.environ/*` (asserted in `test_no_literal_secrets`). ✓
- §7 data flow + error handling (fail-fast env, per-provider FAIL isolation, no secret printing) → Task 3 launcher + Task 4 `classify_completion`/`summarize`. ✓
- §8 CI-safe tests, live smoke separate → Tasks 2/3/4 tests run without keys; live smoke documented in Task 5. ✓
- §9 deliverables + CLAUDE.md edit → Task 1 Step 4. ✓
- §10 acceptance (models list, per-provider completion, ruff+pytest green, no secret in tracked files) → Task 5 gate + `test_no_literal_secrets`. ✓
- §11 Groq ZDR note → comment in `config.yaml` (Task 2 Step 3). ✓

**Placeholder scan:** No TBD/TODO; every code/config step shows full content; version specifiers are bounded ranges (deliberate, installable), not placeholders. ✓

**Type consistency:** `ProbeResult(name, ok, detail)`, `check_models`, `classify_completion`, `summarize`, `_probe_models`, `_probe_completion` are named identically in `healthcheck.py` and `test_healthcheck.py`. `EXPECTED_ALIASES` matches the config aliases and `test_config.py`. `REQUIRED_VARS` in `test_run_proxy.py` matches the `required=(...)` array in `run-proxy.sh` and the keys in `.env.example`. ✓
