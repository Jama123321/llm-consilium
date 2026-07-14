# Phase 3a — `consilium init` Key Wizard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A cross-platform `python -m consilium init` wizard that collects free-tier API keys (hidden entry), writes `~/.config/consilium/.env` idempotently, live-pings each configured provider, and prints a green/red readiness table.

**Architecture:** New `consilium/` package: `providers.py` (static registry), `env_file.py` (idempotent load/write), `init.py` (wizard `run` + `mask` + `live_ping`), `__main__.py` (dispatch). Interactive input and the network ping are injected so tests are hermetic.

**Tech Stack:** Python 3.10, stdlib (`getpass`, `secrets`, `os`), `httpx`, pytest, ruff.

## Global Constraints

- **Secrets:** keys read via `getpass` (hidden), never echoed/logged/printed; only written to `~/.config/consilium/.env` and sent only to their own provider's endpoint. Status shown masked (last-4 only).
- **Cross-platform:** stdlib + httpx; `chmod 0o600` guarded by `os.name == "posix"`.
- **Idempotent:** re-run preserves every existing `KEY=VALUE` (known + unknown); empty entry keeps current value.
- **Ping non-fatal:** a red ping never aborts init; the env file is always written.
- Repo ruff enforces B905/I001/E501 (line-length 100). Python 3.10+; `ruff check .` clean + `pytest -q` green. Commits English imperative, no `Co-Authored-By`. Branch `phase-3a-init`.

## File map

- `consilium/__init__.py`, `consilium/__main__.py`, `consilium/providers.py`, `consilium/env_file.py`, `consilium/init.py` — NEW.
- `pyproject.toml` — add `"consilium"` to `known-first-party`.
- Tests: `tests/test_env_file.py`, `tests/test_providers.py`, `tests/test_init.py` — NEW.

---

### Task 1: `env_file` (idempotent load/write) + ruff first-party

**Files:**
- Modify: `pyproject.toml`
- Create: `consilium/__init__.py`, `consilium/env_file.py`, `tests/test_env_file.py`

**Interfaces:**
- Produces: `env_file.DEFAULT_ENV_PATH`; `load(path) -> dict[str,str]`; `write(path, values) -> None` (templated, preserves all keys, chmod 600 on posix).

- [ ] **Step 1: Add `"consilium"` to `known-first-party` in `pyproject.toml`**

Change the isort line to:
```toml
known-first-party = ["council", "consilium", "consilium_mcp", "healthcheck"]
```

- [ ] **Step 2: Create `consilium/__init__.py` (empty package marker)**

```python
```
(empty file)

- [ ] **Step 3: Write `tests/test_env_file.py`**

```python
import os

from consilium import env_file


def test_load_parses_keys_and_skips_comments(tmp_path):
    p = tmp_path / ".env"
    p.write_text("# comment\nA=1\n\nB = two \n# x\nUNKNOWN_X=zzz\n")
    assert env_file.load(p) == {"A": "1", "B": "two", "UNKNOWN_X": "zzz"}


def test_load_missing_file_returns_empty(tmp_path):
    assert env_file.load(tmp_path / "nope.env") == {}


def test_write_roundtrips_and_preserves_unknown(tmp_path):
    p = tmp_path / ".env"
    values = {"CEREBRAS_API_KEY": "csk-x", "MISTRAL_API_KEY": "m", "LITELLM_MASTER_KEY": "sk-1", "WEIRD": "w"}
    env_file.write(p, values)
    assert env_file.load(p) == values  # every key round-trips, incl. unknown "WEIRD"


def test_write_sets_posix_permissions(tmp_path):
    p = tmp_path / ".env"
    env_file.write(p, {"LITELLM_MASTER_KEY": "sk-1"})
    if os.name == "posix":
        assert (p.stat().st_mode & 0o777) == 0o600
```

- [ ] **Step 4: Run — expect failure**

Run: `.venv/bin/pytest tests/test_env_file.py -q`
Expected: FAIL (module missing).

- [ ] **Step 5: Implement `consilium/env_file.py`**

```python
from __future__ import annotations

import os
from pathlib import Path

DEFAULT_ENV_PATH = Path.home() / ".config" / "consilium" / ".env"

_TIER_A = (
    "CEREBRAS_API_KEY", "GROQ_API_KEY", "CLOUDFLARE_API_TOKEN",
    "CLOUDFLARE_API_BASE", "GITHUB_API_KEY",
)
_TIER_B = ("MISTRAL_API_KEY", "SAMBANOVA_API_KEY", "NVIDIA_NIM_API_KEY")
_KNOWN = set(_TIER_A) | set(_TIER_B) | {"LITELLM_MASTER_KEY"}


def load(path: str | Path = DEFAULT_ENV_PATH) -> dict[str, str]:
    values: dict[str, str] = {}
    p = Path(path)
    if not p.exists():
        return values
    for raw in p.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        values[key.strip()] = val.strip()
    return values


def _group(lines: list[str], title: str, keys, values: dict[str, str]) -> None:
    present = [k for k in keys if k in values]
    if not present:
        return
    lines.append(f"# {title}")
    lines.extend(f"{k}={values[k]}" for k in present)
    lines.append("")


def write(path: str | Path = DEFAULT_ENV_PATH, values: dict[str, str] | None = None) -> None:
    data = dict(values or {})
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Consilium secrets — managed by `python -m consilium init`. chmod 600.", ""]
    _group(lines, "Tier A (safe for any prompt — no-train)", _TIER_A, data)
    _group(lines, "Tier B (public prompts only)", _TIER_B, data)
    _group(lines, "Proxy auth", ("LITELLM_MASTER_KEY",), data)
    _group(lines, "Other", [k for k in data if k not in _KNOWN], data)
    p.write_text("\n".join(lines).rstrip() + "\n")
    if os.name == "posix":
        p.chmod(0o600)
```

- [ ] **Step 6: Run — expect pass**

Run: `.venv/bin/ruff check pyproject.toml consilium/ tests/test_env_file.py && .venv/bin/pytest tests/test_env_file.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml consilium/__init__.py consilium/env_file.py tests/test_env_file.py
git commit -m "feat(3a): idempotent env-file read/write for the init wizard"
```

---

### Task 2: Provider registry

**Files:**
- Create: `consilium/providers.py`, `tests/test_providers.py`

**Interfaces:**
- Consumes: nothing (pure data). Produces: `Provider` dataclass + `PROVIDERS: tuple[Provider, ...]`.

- [ ] **Step 1: Write `tests/test_providers.py`**

```python
from consilium.providers import PROVIDERS, Provider


def test_registry_covers_seven_providers():
    keys = {p.key for p in PROVIDERS}
    assert keys == {"cerebras", "groq", "cloudflare", "github", "mistral", "sambanova", "nvidia"}


def test_each_provider_well_formed():
    for p in PROVIDERS:
        assert isinstance(p, Provider)
        assert p.tier in {"A", "B"}
        assert p.env_vars and all(v.isupper() for v in p.env_vars)
        assert p.signup and p.ping_model


def test_cloudflare_needs_token_and_base():
    cf = next(p for p in PROVIDERS if p.key == "cloudflare")
    assert cf.env_vars == ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_API_BASE")


def test_tiers_match_project_policy():
    tier = {p.key: p.tier for p in PROVIDERS}
    assert tier["cerebras"] == tier["groq"] == tier["cloudflare"] == tier["github"] == "A"
    assert tier["mistral"] == tier["sambanova"] == tier["nvidia"] == "B"
```

- [ ] **Step 2: Run — expect failure**

Run: `.venv/bin/pytest tests/test_providers.py -q`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement `consilium/providers.py`**

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Provider:
    key: str
    name: str
    tier: str
    env_vars: tuple[str, ...]
    signup: str
    ping_base_url: str  # for cloudflare, the base comes from CLOUDFLARE_API_BASE at ping time
    ping_model: str


PROVIDERS: tuple[Provider, ...] = (
    Provider(
        "cerebras", "Cerebras", "A", ("CEREBRAS_API_KEY",),
        "cloud.cerebras.ai -> API Keys (free, 1M tokens/day)",
        "https://api.cerebras.ai/v1", "zai-glm-4.7",
    ),
    Provider(
        "groq", "Groq", "A", ("GROQ_API_KEY",),
        "console.groq.com -> API Keys (free)",
        "https://api.groq.com/openai/v1", "llama-3.3-70b-versatile",
    ),
    Provider(
        "cloudflare", "Cloudflare Workers AI", "A",
        ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_API_BASE"),
        "dash.cloudflare.com -> My Profile -> API Tokens -> 'Workers AI' template; "
        "API base https://api.cloudflare.com/client/v4/accounts/<id>/ai/v1",
        "", "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
    ),
    Provider(
        "github", "GitHub Models", "A", ("GITHUB_API_KEY",),
        "github.com -> Settings -> Developer settings -> fine-grained token, Models: Read",
        "https://models.github.ai/inference", "openai/gpt-4.1-mini",
    ),
    Provider(
        "mistral", "Mistral", "B", ("MISTRAL_API_KEY",),
        "console.mistral.ai -> API Keys (free; trains on prompts -> Tier B)",
        "https://api.mistral.ai/v1", "mistral-small-latest",
    ),
    Provider(
        "sambanova", "SambaNova", "B", ("SAMBANOVA_API_KEY",),
        "cloud.sambanova.ai -> API Keys (free)",
        "https://api.sambanova.ai/v1", "Meta-Llama-3.3-70B-Instruct",
    ),
    Provider(
        "nvidia", "NVIDIA NIM", "B", ("NVIDIA_NIM_API_KEY",),
        "build.nvidia.com -> API Key (free credits)",
        "https://integrate.api.nvidia.com/v1", "meta/llama-3.3-70b-instruct",
    ),
)
```

- [ ] **Step 4: Run — expect pass**

Run: `.venv/bin/ruff check consilium/providers.py tests/test_providers.py && .venv/bin/pytest tests/test_providers.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add consilium/providers.py tests/test_providers.py
git commit -m "feat(3a): free-provider registry for the init wizard"
```

---

### Task 3: The wizard (`init`) + entrypoint

**Files:**
- Create: `consilium/init.py`, `consilium/__main__.py`, `tests/test_init.py`

**Interfaces:**
- Consumes: `env_file`, `providers`.
- Produces: `init.mask(str)->str`; `init.PingResult(ok,detail)`; `init.live_ping(provider, env, *, client=None) -> PingResult`; `init.run(*, env_path, prompt, echo, ping) -> int`.

- [ ] **Step 1: Write `tests/test_init.py`**

```python
import httpx

from consilium import env_file, init
from consilium.providers import PROVIDERS


def test_mask_hides_secret():
    assert init.mask("") == "not set"
    assert init.mask("csk-abcd1234")[-4:] == "1234"
    assert "abcd1234" not in init.mask("csk-abcd1234")  # full value never shown


def test_live_ping_ok_and_error():
    def handler(request):
        return httpx.Response(200 if "good" in request.headers["authorization"] else 401)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    groq = next(p for p in PROVIDERS if p.key == "groq")
    assert init.live_ping(groq, {"GROQ_API_KEY": "good"}, client=client).ok is True
    assert init.live_ping(groq, {"GROQ_API_KEY": "bad"}, client=client).ok is False


def test_run_writes_keys_and_reports_readiness(tmp_path, capsys):
    p = tmp_path / ".env"
    # scripted answers: one per env_var across all providers, in order.
    # cerebras, groq, cloudflare(token, base), github, mistral, sambanova, nvidia
    answers = iter(["csk-cere", "gsk-groq", "", "", "", "", "", ""])
    lines: list[str] = []

    def prompt(_msg):
        return next(answers)

    def ping(provider, env):
        return init.PingResult(ok=True, detail="ok")

    rc = init.run(env_path=p, prompt=prompt, echo=lines.append, ping=ping)
    assert rc == 0
    saved = env_file.load(p)
    assert saved["CEREBRAS_API_KEY"] == "csk-cere" and saved["GROQ_API_KEY"] == "gsk-groq"
    assert saved["LITELLM_MASTER_KEY"].startswith("sk-")  # generated
    # only providers with all keys are pinged; cloudflare (token+base skipped) is dormant
    joined = "\n".join(lines)
    assert "Cerebras" in joined and "dormant" in joined
    assert "csk-cere" not in joined and "gsk-groq" not in joined  # secrets never echoed


def test_run_keeps_existing_master_and_unknown(tmp_path):
    p = tmp_path / ".env"
    env_file.write(p, {"LITELLM_MASTER_KEY": "sk-keepme", "WEIRD": "w"})
    rc = init.run(env_path=p, prompt=lambda _m: "", echo=lambda _l: None,
                  ping=lambda _p, _e: init.PingResult(True, "ok"))
    assert rc == 0
    saved = env_file.load(p)
    assert saved["LITELLM_MASTER_KEY"] == "sk-keepme"  # preserved, not regenerated
    assert saved["WEIRD"] == "w"  # unknown key preserved
```

- [ ] **Step 2: Run — expect failure**

Run: `.venv/bin/pytest tests/test_init.py -q`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement `consilium/init.py`**

```python
from __future__ import annotations

import getpass
import secrets
from dataclasses import dataclass

import httpx

from consilium import env_file
from consilium.providers import PROVIDERS, Provider


@dataclass(frozen=True)
class PingResult:
    ok: bool
    detail: str


def mask(value: str) -> str:
    if not value:
        return "not set"
    return f"set (...{value[-4:]})" if len(value) >= 4 else "set (...)"


def live_ping(
    provider: Provider, env: dict[str, str], *, client: httpx.Client | None = None
) -> PingResult:
    key = env.get(provider.env_vars[0], "")
    if not key:
        return PingResult(False, "no key")
    base = env.get("CLOUDFLARE_API_BASE", "") if provider.key == "cloudflare" else provider.ping_base_url
    if not base:
        return PingResult(False, "no base url")
    owns_client = client is None
    client = client or httpx.Client(timeout=15.0)
    try:
        resp = client.post(
            f"{base.rstrip('/')}/chat/completions",
            json={"model": provider.ping_model,
                  "messages": [{"role": "user", "content": "ping"}], "max_tokens": 1},
            headers={"Authorization": f"Bearer {key}"},
        )
    except httpx.HTTPError as exc:
        return PingResult(False, f"unreachable: {exc.__class__.__name__}")
    finally:
        if owns_client:
            client.close()
    if resp.status_code // 100 == 2:
        return PingResult(True, "ok")
    return PingResult(False, f"HTTP {resp.status_code}")


def run(*, env_path=env_file.DEFAULT_ENV_PATH, prompt=getpass.getpass, echo=print,
        ping=live_ping) -> int:
    existing = env_file.load(env_path)
    collected: dict[str, str] = {}
    for provider in PROVIDERS:
        echo(f"\n{provider.name}  [Tier {provider.tier}]  - {provider.signup}")
        for var in provider.env_vars:
            entered = prompt(f"  {var} [{mask(existing.get(var, ''))}] (Enter to keep): ").strip()
            if entered:
                collected[var] = entered
    merged = {**existing, **collected}
    if not merged.get("LITELLM_MASTER_KEY"):
        merged["LITELLM_MASTER_KEY"] = f"sk-{secrets.token_hex(24)}"
    env_file.write(env_path, merged)
    echo(f"\nWrote {env_path}")
    echo("\nReadiness:")
    for provider in PROVIDERS:
        if all(merged.get(v) for v in provider.env_vars):
            res = ping(provider, merged)
            echo(f"  {'green' if res.ok else 'red'} {provider.name}: {res.detail}")
        else:
            echo(f"  dormant {provider.name}: no key")
    return 0
```

- [ ] **Step 4: Implement `consilium/__main__.py`**

```python
from __future__ import annotations

import sys

from consilium import init


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args and args[0] == "init":
        return init.run()
    print("usage: python -m consilium init")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run — expect pass (full gate)**

Run: `.venv/bin/ruff check . && .venv/bin/pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add consilium/init.py consilium/__main__.py tests/test_init.py
git commit -m "feat(3a): interactive key wizard with live readiness ping"
```

---

## Self-review

**Spec coverage:** provider registry → T2; idempotent env-file (load/write, chmod-posix, preserve unknown) → T1; wizard (`mask`, `live_ping`, `run` with hidden prompt, master-key gen/preserve, readiness table) → T3; `python -m consilium init` entrypoint → T3; ruff first-party → T1. Secrets discipline (getpass, mask, never echo — asserted by `"csk-cere" not in joined`), ping non-fatal, cross-platform chmod guard → all covered.

**Placeholder scan:** none — complete code/commands in every step. Ping model ids are current-as-of-2c (drift acknowledged in the spec; a red ping is informational).

**Type consistency:** `Provider(key,name,tier,env_vars,signup,ping_base_url,ping_model)` defined T2, consumed T3. `env_file.load/write/DEFAULT_ENV_PATH` T1 ↔ T3. `init.run(*, env_path, prompt, echo, ping)`, `live_ping(provider, env, *, client=None)`, `mask`, `PingResult(ok,detail)` consistent T3 ↔ tests. `__main__.main` calls `init.run`.
