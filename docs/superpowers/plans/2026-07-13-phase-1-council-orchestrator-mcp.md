# Phase 1 — Council Orchestrator + MCP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the council orchestrator (`ask` + `council`) over the Phase-0 proxy and expose it as a user-scope MCP server with a usage protocol.

**Architecture:** A `council/` package of small async modules (registry → privacy → router → client → fanout → aggregate → orchestrator), all talking to the LiteLLM proxy at `127.0.0.1:4000/v1`. A thin `consilium_mcp/` server adapts the orchestrator into two MCP tools. CI-safe tests inject fake async callers; a live smoke script exercises the real proxy.

**Tech Stack:** Python 3.10, `asyncio`/`httpx`, PyYAML, MCP Python SDK (`mcp`), `pytest`/`ruff`.

## Global Constraints

- Python 3.10; repo-local `.venv`; invoke tools as `.venv/bin/<tool>`.
- **Tier-A only** today; the privacy gate is enforced regardless (`sensitive` → tier A; `public` → A+B). `sensitivity` default = `sensitive`.
- **Secrets never literal** in code/config/logs/git. The MCP server reads `LITELLM_MASTER_KEY` from env or `~/.config/consilium/.env`; never logs it. Prompts logged only at debug and only for Tier-A targets.
- The 5 proxy aliases are exactly: `council/cerebras-glm-4.7`, `council/cerebras-gpt-oss-120b`, `council/groq-llama-70b`, `council/groq-gpt-oss-120b`, `council/cloudflare-llama-70b`.
- Capability vocabulary: `{reasoning, code, fast, general}`. Member metadata lives in `proxy/config.yaml` `model_info`.
- Constants: `DEFAULT_BASE_URL = "http://127.0.0.1:4000/v1"`, `CLASSIFIER_ALIAS = "council/groq-llama-70b"`, `CHAIR_ALIAS = "council/cerebras-glm-4.7"`, `DEFAULT_MEMBER_ALIASES = ("council/cerebras-glm-4.7", "council/groq-gpt-oss-120b", "council/cloudflare-llama-70b")`.
- **Naming note:** the MCP package is `consilium_mcp/` (NOT `mcp/`) — a top-level `mcp/` would shadow the installed `mcp` SDK. This deviates from CLAUDE.md's structure diagram deliberately.
- Commits: English, imperative, **NO `Co-Authored-By` trailer**. Never `--no-verify`/force-push. Stay on branch `phase-1-council-mcp`; do not merge to main.
- Async tests use `asyncio.run(...)` in sync test functions (no `pytest-asyncio` dependency).

## File Structure

| Path | Responsibility | Task |
|---|---|---|
| `requirements.txt` (mod) | add `mcp>=1.0` | 1 |
| `pyproject.toml` (mod) | pythonpath `[".","scripts"]`; isort first-party | 1 |
| `council/__init__.py`, `consilium_mcp/__init__.py` | packages | 1 |
| `council/types.py` | shared frozen dataclasses + `AsyncCaller` alias | 1 |
| `council/errors.py` | typed exceptions | 1 |
| `proxy/config.yaml` (mod) | add `capabilities`/`strength` to each `model_info` | 2 |
| `council/registry.py` | load `Member`s from config | 2 |
| `council/privacy.py` | secret-scan + tier filter | 3 |
| `council/client.py` | async single-member proxy call | 4 |
| `council/router.py` | classify prompt + select member | 5 |
| `council/fanout.py` | parallel fan-out | 6 |
| `council/aggregate.py` | adaptive judge/vote | 7 |
| `council/orchestrator.py` | `ask()` + `council()` | 8 |
| `scripts/council-smoke.py` | live dev smoke | 8 |
| `consilium_mcp/server.py` | MCP tools `ask` + `council` | 9 |
| `docs/usage-rule.md` | text to append to `~/.claude/CLAUDE.md` + `claude mcp add` cmd | 10 |
| `council/README.md` | run/registration docs | 10 |

---

## Sub-wave 1a — Engine (Tasks 1–8)

### Task 1: Package scaffold, deps, shared types & errors

**Files:**
- Modify: `requirements.txt`, `pyproject.toml`
- Create: `council/__init__.py`, `consilium_mcp/__init__.py`, `council/types.py`, `council/errors.py`, `tests/test_types.py`

**Interfaces:**
- Produces: `AsyncCaller = Callable[[str, str], Awaitable[str]]`; dataclasses `Member(alias, privacy_tier, capabilities, strength, rpm)`, `MemberAnswer(alias, ok, answer, detail)`, `AskResult(answer, model_used, capability, note)`, `CouncilResult(answer, per_member, disagreements, judge_used, mode)`; errors `ConsiliumError`(base), `PrivacyRefusal`, `NoEligibleMember`, `AllMembersFailed`, `MemberCallError(alias, detail)`.

- [ ] **Step 1: Add the `mcp` dependency**

Edit `requirements.txt` — add one line after `ruff>=0.6`:
```
mcp>=1.0
```

- [ ] **Step 2: Update `pyproject.toml`**

Replace the isort and pytest sections:
```toml
[tool.ruff.lint.isort]
known-first-party = ["council", "consilium_mcp", "healthcheck"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = [".", "scripts"]
```

- [ ] **Step 3: Install the new dep**

Run: `.venv/bin/pip install -r requirements.txt`
Expected: `mcp` installs; `.venv/bin/python -c "import mcp; print('ok')"` → `ok`. (Network required; disable the sandbox for this install command if needed.)

- [ ] **Step 4: Create the empty package markers**

Create `council/__init__.py` (empty) and `consilium_mcp/__init__.py` (empty).

- [ ] **Step 5: Write the failing test**

Create `tests/test_types.py`:
```python
import dataclasses

import pytest

from council.errors import (
    AllMembersFailed,
    ConsiliumError,
    MemberCallError,
    NoEligibleMember,
    PrivacyRefusal,
)
from council.types import AskResult, CouncilResult, Member, MemberAnswer


def test_member_is_frozen():
    m = Member(alias="a", privacy_tier="A", capabilities=("general",), strength=3, rpm=5)
    with pytest.raises(dataclasses.FrozenInstanceError):
        m.strength = 4


def test_result_types_construct():
    ask = AskResult(answer="x", model_used="a", capability="code", note="n")
    council = CouncilResult(
        answer="x", per_member=[], disagreements="", judge_used=None, mode="vote"
    )
    ans = MemberAnswer(alias="a", ok=True, answer="x", detail="ok")
    assert ask.answer == "x" and council.mode == "vote" and ans.ok


def test_errors_subclass_base():
    for exc in (PrivacyRefusal, NoEligibleMember, AllMembersFailed, MemberCallError):
        assert issubclass(exc, ConsiliumError)


def test_member_call_error_carries_detail():
    e = MemberCallError("council/x", "429 rate-limited")
    assert e.alias == "council/x" and e.detail == "429 rate-limited"
```

- [ ] **Step 6: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_types.py -q`
Expected: FAIL — `council.types` / `council.errors` do not exist.

- [ ] **Step 7: Create `council/errors.py`**

```python
class ConsiliumError(Exception):
    """Base class for all council errors."""


class PrivacyRefusal(ConsiliumError):
    """Prompt contains a secret, or no member satisfies the required tier."""


class NoEligibleMember(ConsiliumError):
    """No member has the requested capability."""


class AllMembersFailed(ConsiliumError):
    """Every fan-out member abstained."""


class MemberCallError(ConsiliumError):
    """A single member call failed (non-200 / timeout)."""

    def __init__(self, alias: str, detail: str) -> None:
        super().__init__(f"{alias}: {detail}")
        self.alias = alias
        self.detail = detail
```

- [ ] **Step 8: Create `council/types.py`**

```python
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

# (alias, prompt) -> answer text
AsyncCaller = Callable[[str, str], Awaitable[str]]


@dataclass(frozen=True)
class Member:
    alias: str
    privacy_tier: str
    capabilities: tuple[str, ...]
    strength: int
    rpm: int


@dataclass(frozen=True)
class MemberAnswer:
    alias: str
    ok: bool
    answer: str | None
    detail: str


@dataclass(frozen=True)
class AskResult:
    answer: str
    model_used: str
    capability: str | None
    note: str


@dataclass(frozen=True)
class CouncilResult:
    answer: str
    per_member: list[MemberAnswer]
    disagreements: str
    judge_used: str | None
    mode: str
```

- [ ] **Step 9: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_types.py -q`
Expected: PASS (4 tests).

- [ ] **Step 10: Lint & commit**

```bash
.venv/bin/ruff check .
git add requirements.txt pyproject.toml council/ consilium_mcp/ tests/test_types.py
git commit -m "feat: scaffold council package with shared types and errors"
```
Expected: ruff `All checks passed!`.

---

### Task 2: Member registry + capability tags in config

**Files:**
- Modify: `proxy/config.yaml`
- Create: `council/registry.py`, `tests/test_registry.py`

**Interfaces:**
- Consumes: `Member` (Task 1).
- Produces: `registry.load_members(config_path: str | Path) -> list[Member]`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_registry.py`:
```python
from pathlib import Path

from council import registry

CONFIG = Path(__file__).resolve().parents[1] / "proxy" / "config.yaml"


def _members():
    return {m.alias: m for m in registry.load_members(CONFIG)}


def test_loads_all_five_members():
    assert set(_members()) == {
        "council/cerebras-glm-4.7",
        "council/cerebras-gpt-oss-120b",
        "council/groq-llama-70b",
        "council/groq-gpt-oss-120b",
        "council/cloudflare-llama-70b",
    }


def test_capabilities_and_strength_parsed():
    glm = _members()["council/cerebras-glm-4.7"]
    assert glm.privacy_tier == "A"
    assert glm.strength == 5
    assert "reasoning" in glm.capabilities


def test_rpm_defaults_when_absent():
    # cloudflare alias has no rpm in config -> default 10
    assert _members()["council/cloudflare-llama-70b"].rpm == 10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_registry.py -q`
Expected: FAIL — `council.registry` missing (and config lacks capabilities/strength).

- [ ] **Step 3: Overwrite `proxy/config.yaml` with capability tags added**

```yaml
# Consilium LiteLLM proxy — Phase 0 (Tier-A providers only).
# Secrets are referenced via os.environ/* and loaded from ~/.config/consilium/.env.
# The privacy_tier tags are read by the Phase 1 council privacy gate;
# capabilities/strength are read by the Phase 1 router and council.
model_list:
  # Cerebras free catalog drifted from the 2026 audit (qwen-3-235b / llama-3.3-70b
  # no longer offered); pinned to live ids verified via GET api.cerebras.ai/v1/models.
  # NOTE on tier: privacy_tier follows the INFERENCE PROVIDER (Cerebras: no-train /
  # no-retain ToS), not the weights' origin. zai-glm-4.7 runs on Cerebras, so Zhipu
  # never sees the prompt -> Tier-A. (Tier-B for GLM would apply only to a direct
  # open.bigmodel.cn call.)
  - model_name: council/cerebras-glm-4.7
    litellm_params:
      model: cerebras/zai-glm-4.7
      api_key: os.environ/CEREBRAS_API_KEY
      rpm: 5
    model_info:
      privacy_tier: A
      strength: 5
      capabilities: [reasoning, general, code]
  - model_name: council/cerebras-gpt-oss-120b
    litellm_params:
      model: cerebras/gpt-oss-120b
      api_key: os.environ/CEREBRAS_API_KEY
      rpm: 5
    model_info:
      privacy_tier: A
      strength: 4
      capabilities: [reasoning, code, general]
  - model_name: council/groq-llama-70b
    litellm_params:
      model: groq/llama-3.3-70b-versatile
      api_key: os.environ/GROQ_API_KEY
      rpm: 30
    model_info:
      privacy_tier: A
      strength: 3
      capabilities: [general, fast, code]
  # Groq free tier: does NOT train on prompts (the Tier-A criterion); default keeps
  # 7-day operational logs — full zero-retention needs ZDR (later action, non-blocking).
  - model_name: council/groq-gpt-oss-120b
    litellm_params:
      model: groq/openai/gpt-oss-120b
      api_key: os.environ/GROQ_API_KEY
      rpm: 30
    model_info:
      privacy_tier: A
      strength: 4
      capabilities: [reasoning, code, general, fast]
  - model_name: council/cloudflare-llama-70b
    litellm_params:
      model: openai/@cf/meta/llama-3.3-70b-instruct-fp8-fast
      api_base: os.environ/CLOUDFLARE_API_BASE
      api_key: os.environ/CLOUDFLARE_API_TOKEN
    model_info:
      privacy_tier: A
      strength: 3
      capabilities: [general, fast]
router_settings:
  num_retries: 1
general_settings:
  master_key: os.environ/LITELLM_MASTER_KEY
```

- [ ] **Step 4: Create `council/registry.py`**

```python
from __future__ import annotations

from pathlib import Path

import yaml

from council.types import Member


def load_members(config_path: str | Path) -> list[Member]:
    data = yaml.safe_load(Path(config_path).read_text())
    members: list[Member] = []
    for entry in data.get("model_list", []):
        info = entry.get("model_info") or {}
        params = entry.get("litellm_params") or {}
        members.append(
            Member(
                alias=entry["model_name"],
                privacy_tier=info.get("privacy_tier", "B"),
                capabilities=tuple(info.get("capabilities", ["general"])),
                strength=int(info.get("strength", 1)),
                rpm=int(params.get("rpm", 10)),
            )
        )
    return members
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_registry.py tests/test_config.py -q`
Expected: PASS (registry 3 + the Phase-0 config tests still green — the additions are additive).

- [ ] **Step 6: Lint & commit**

```bash
.venv/bin/ruff check .
git add proxy/config.yaml council/registry.py tests/test_registry.py
git commit -m "feat: add capability tags and member registry loader"
```

---

### Task 3: Privacy gate (secret-scan + tier filter)

**Files:**
- Create: `council/privacy.py`, `tests/test_privacy.py`

**Interfaces:**
- Consumes: `Member` (Task 1), `PrivacyRefusal` (Task 1).
- Produces: `privacy.scan_secrets(prompt: str) -> None`; `privacy.allowed_members(members, sensitivity) -> list[Member]`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_privacy.py`:
```python
import pytest

from council import privacy
from council.errors import PrivacyRefusal
from council.types import Member

A = Member("a", "A", ("general",), 3, 5)
B = Member("b", "B", ("general",), 3, 5)


def test_scan_passes_clean_prompt():
    privacy.scan_secrets("please refactor this pure function")  # no raise


@pytest.mark.parametrize(
    "bad",
    [
        "here is my key sk-abcdefghijklmnop12345",
        "CEREBRAS csk-abcdefghijklmnop12345",
        "token gsk_abcdefghijklmnop12345",
        "-----BEGIN RSA PRIVATE KEY-----",
        "OPENAI_API_KEY=supersecretvalue",
    ],
)
def test_scan_refuses_secrets(bad):
    with pytest.raises(PrivacyRefusal):
        privacy.scan_secrets(bad)


def test_sensitive_keeps_only_tier_a():
    assert privacy.allowed_members([A, B], "sensitive") == [A]


def test_public_keeps_all():
    assert privacy.allowed_members([A, B], "public") == [A, B]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_privacy.py -q`
Expected: FAIL — `council.privacy` missing.

- [ ] **Step 3: Create `council/privacy.py`**

```python
from __future__ import annotations

import re

from council.errors import PrivacyRefusal
from council.types import Member

_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9]{16,}"),
    re.compile(r"\bcsk-[A-Za-z0-9]{16,}"),
    re.compile(r"\bgsk_[A-Za-z0-9]{16,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?im)^\s*[A-Z0-9_]*(?:API_KEY|SECRET|TOKEN|PASSWORD)\s*="),
)


def scan_secrets(prompt: str) -> None:
    for pat in _SECRET_PATTERNS:
        if pat.search(prompt):
            raise PrivacyRefusal(
                "prompt appears to contain a secret; strip credentials before "
                "consulting the council"
            )


def allowed_members(members: list[Member], sensitivity: str) -> list[Member]:
    if sensitivity == "public":
        return list(members)
    return [m for m in members if m.privacy_tier == "A"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_privacy.py -q`
Expected: PASS (2 + 5 parametrized = 6 tests).

- [ ] **Step 5: Lint & commit**

```bash
.venv/bin/ruff check .
git add council/privacy.py tests/test_privacy.py
git commit -m "feat: add privacy gate with secret-scan and tier filter"
```

---

### Task 4: Proxy client (async single-member call)

**Files:**
- Create: `council/client.py`, `tests/test_client.py`

**Interfaces:**
- Consumes: `MemberCallError`, `AsyncCaller` (Task 1).
- Produces: `client.complete(base_url, api_key, alias, prompt, *, max_tokens=512, timeout=30.0, transport=None) -> str` (async; raises `MemberCallError`); `client.make_caller(base_url, api_key, *, max_tokens=512, timeout=30.0) -> AsyncCaller`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_client.py`:
```python
import asyncio

import httpx
import pytest

from council import client
from council.errors import MemberCallError


def _transport(status, body=None):
    def handler(request):
        return httpx.Response(status, json=body or {})

    return httpx.MockTransport(handler)


def test_complete_returns_answer_on_200():
    body = {"choices": [{"message": {"content": "hello"}}]}
    out = asyncio.run(
        client.complete("http://x/v1", "k", "council/a", "hi", transport=_transport(200, body))
    )
    assert out == "hello"


@pytest.mark.parametrize("status,frag", [(401, "401"), (429, "429"), (500, "HTTP 500")])
def test_complete_maps_errors(status, frag):
    with pytest.raises(MemberCallError) as ei:
        asyncio.run(
            client.complete("http://x/v1", "k", "council/a", "hi", transport=_transport(status))
        )
    assert frag in ei.value.detail
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_client.py -q`
Expected: FAIL — `council.client` missing.

- [ ] **Step 3: Create `council/client.py`**

```python
from __future__ import annotations

import functools

import httpx

from council.errors import MemberCallError
from council.types import AsyncCaller


async def complete(
    base_url: str,
    api_key: str,
    alias: str,
    prompt: str,
    *,
    max_tokens: int = 512,
    timeout: float = 30.0,
    transport: httpx.AsyncBaseTransport | None = None,
) -> str:
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {
        "model": alias,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
    }
    try:
        async with httpx.AsyncClient(
            base_url=base_url, headers=headers, timeout=timeout, transport=transport
        ) as http:
            resp = await http.post("/chat/completions", json=payload)
    except httpx.TimeoutException as exc:
        raise MemberCallError(alias, "timeout") from exc
    except httpx.HTTPError as exc:
        raise MemberCallError(alias, f"request error: {exc.__class__.__name__}") from exc
    if resp.status_code != 200:
        detail = {401: "401 auth failed", 429: "429 rate-limited"}.get(
            resp.status_code, f"HTTP {resp.status_code}"
        )
        raise MemberCallError(alias, detail)
    return resp.json()["choices"][0]["message"]["content"]


def make_caller(
    base_url: str, api_key: str, *, max_tokens: int = 512, timeout: float = 30.0
) -> AsyncCaller:
    return functools.partial(
        complete, base_url, api_key, max_tokens=max_tokens, timeout=timeout
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_client.py -q`
Expected: PASS (1 + 3 parametrized = 4 tests).

- [ ] **Step 5: Lint & commit**

```bash
.venv/bin/ruff check .
git add council/client.py tests/test_client.py
git commit -m "feat: add async proxy client with typed call errors"
```

---

### Task 5: Router (classify + select)

**Files:**
- Create: `council/router.py`, `tests/test_router.py`

**Interfaces:**
- Consumes: `Member`, `AsyncCaller`, `NoEligibleMember` (Task 1).
- Produces: `router.classify(prompt, *, caller, classifier_alias) -> str` (async); `router.select(members, capability) -> Member`; constant `router.CAPABILITIES`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_router.py`:
```python
import asyncio

from council import router
from council.types import Member

STRONG = Member("strong", "A", ("reasoning", "general"), 5, 5)
FAST = Member("fast", "A", ("fast", "general"), 3, 30)
CODER = Member("coder", "A", ("code",), 4, 10)
MEMBERS = [STRONG, FAST, CODER]


def test_select_picks_highest_strength_with_capability():
    assert router.select(MEMBERS, "reasoning") is STRONG


def test_select_tie_breaks_on_rpm():
    a = Member("a", "A", ("general",), 3, 5)
    b = Member("b", "A", ("general",), 3, 30)
    assert router.select([a, b], "general") is b


def test_select_raises_when_no_capability():
    import pytest

    from council.errors import NoEligibleMember

    with pytest.raises(NoEligibleMember):
        router.select(MEMBERS, "vision")


def test_classify_normalizes_label():
    async def fake(alias, prompt):
        return "This is clearly a REASONING task."

    cap = asyncio.run(router.classify("solve x", caller=fake, classifier_alias="c"))
    assert cap == "reasoning"


def test_classify_defaults_to_general_on_unknown():
    async def fake(alias, prompt):
        return "banana"

    cap = asyncio.run(router.classify("hi", caller=fake, classifier_alias="c"))
    assert cap == "general"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_router.py -q`
Expected: FAIL — `council.router` missing.

- [ ] **Step 3: Create `council/router.py`**

```python
from __future__ import annotations

from council.errors import NoEligibleMember
from council.types import AsyncCaller, Member

CAPABILITIES = ("reasoning", "code", "fast", "general")

_CLASSIFY_PROMPT = (
    "Classify the task below into exactly one word from this list: "
    "reasoning, code, fast, general. Reply with only that word.\n\nTask:\n{prompt}"
)


def _normalize_capability(text: str) -> str:
    low = text.strip().lower()
    for cap in CAPABILITIES:
        if cap in low:
            return cap
    return "general"


async def classify(prompt: str, *, caller: AsyncCaller, classifier_alias: str) -> str:
    raw = await caller(classifier_alias, _CLASSIFY_PROMPT.format(prompt=prompt))
    return _normalize_capability(raw)


def select(members: list[Member], capability: str) -> Member:
    candidates = [m for m in members if capability in m.capabilities]
    if not candidates:
        raise NoEligibleMember(f"no member has capability '{capability}'")
    return max(candidates, key=lambda m: (m.strength, m.rpm))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_router.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Lint & commit**

```bash
.venv/bin/ruff check .
git add council/router.py tests/test_router.py
git commit -m "feat: add capability router (classify + select)"
```

---

### Task 6: Fan-out (parallel member calls)

**Files:**
- Create: `council/fanout.py`, `tests/test_fanout.py`

**Interfaces:**
- Consumes: `Member`, `MemberAnswer`, `AsyncCaller`, `MemberCallError` (Task 1).
- Produces: `fanout.fan_out(prompt, members, caller, *, timeout=30.0) -> list[MemberAnswer]` (async).

- [ ] **Step 1: Write the failing test**

Create `tests/test_fanout.py`:
```python
import asyncio

from council import fanout
from council.errors import MemberCallError
from council.types import Member

M1 = Member("m1", "A", ("general",), 3, 5)
M2 = Member("m2", "A", ("general",), 3, 5)


def test_all_ok():
    async def caller(alias, prompt):
        return f"ans-{alias}"

    res = {a.alias: a for a in asyncio.run(fanout.fan_out("q", [M1, M2], caller))}
    assert res["m1"].ok and res["m1"].answer == "ans-m1"
    assert res["m2"].ok


def test_one_abstains_on_call_error():
    async def caller(alias, prompt):
        if alias == "m2":
            raise MemberCallError("m2", "429 rate-limited")
        return "ok"

    res = {a.alias: a for a in asyncio.run(fanout.fan_out("q", [M1, M2], caller))}
    assert res["m1"].ok
    assert not res["m2"].ok and res["m2"].answer is None and "429" in res["m2"].detail


def test_slow_member_times_out():
    async def caller(alias, prompt):
        if alias == "m2":
            await asyncio.sleep(1)
        return "ok"

    res = {a.alias: a for a in asyncio.run(fanout.fan_out("q", [M1, M2], caller, timeout=0.05))}
    assert res["m1"].ok
    assert not res["m2"].ok and res["m2"].detail == "timeout"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_fanout.py -q`
Expected: FAIL — `council.fanout` missing.

- [ ] **Step 3: Create `council/fanout.py`**

```python
from __future__ import annotations

import asyncio

from council.errors import MemberCallError
from council.types import AsyncCaller, Member, MemberAnswer


async def _call_one(
    member: Member, prompt: str, caller: AsyncCaller, sem: asyncio.Semaphore, timeout: float
) -> MemberAnswer:
    async with sem:
        try:
            answer = await asyncio.wait_for(caller(member.alias, prompt), timeout)
        except MemberCallError as exc:
            return MemberAnswer(member.alias, ok=False, answer=None, detail=exc.detail)
        except (asyncio.TimeoutError, TimeoutError):
            return MemberAnswer(member.alias, ok=False, answer=None, detail="timeout")
        return MemberAnswer(member.alias, ok=True, answer=answer, detail="ok")


async def fan_out(
    prompt: str, members: list[Member], caller: AsyncCaller, *, timeout: float = 30.0
) -> list[MemberAnswer]:
    # Per-member semaphore (sized to rpm) guards against saturating a member when the
    # same member is called concurrently; harmless at one-call-per-member.
    sems = {m.alias: asyncio.Semaphore(max(1, m.rpm)) for m in members}
    tasks = [
        asyncio.create_task(_call_one(m, prompt, caller, sems[m.alias], timeout)) for m in members
    ]
    return list(await asyncio.gather(*tasks))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_fanout.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Lint & commit**

```bash
.venv/bin/ruff check .
git add council/fanout.py tests/test_fanout.py
git commit -m "feat: add parallel fan-out with per-member timeout and abstain"
```

---

### Task 7: Aggregate (adaptive judge/vote)

**Files:**
- Create: `council/aggregate.py`, `tests/test_aggregate.py`

**Interfaces:**
- Consumes: `MemberAnswer`, `AsyncCaller`, `AllMembersFailed` (Task 1).
- Produces: `aggregate.aggregate(prompt, answers, *, caller, judge_alias) -> tuple[str, str, str]` (async) returning `(answer, mode, disagreements)` where `mode ∈ {"vote","judge"}`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_aggregate.py`:
```python
import asyncio

import pytest

from council import aggregate
from council.errors import AllMembersFailed
from council.types import MemberAnswer


def _answers(*pairs):
    return [MemberAnswer(a, ok=ok, answer=ans, detail="ok" if ok else "x") for a, ok, ans in pairs]


async def _judge(alias, prompt):
    return "Merged best answer.\nDISAGREEMENTS: candidate 2 differed on scope."


def test_vote_on_closed_form():
    ans = _answers(("m1", True, "Yes"), ("m2", True, "yes"), ("m3", True, "No"))
    out, mode, dis = asyncio.run(
        aggregate.aggregate("q", ans, caller=_judge, judge_alias="chair")
    )
    assert mode == "vote" and out == "yes" and dis == ""


def test_judge_on_open_ended():
    ans = _answers(
        ("m1", True, "A long detailed explanation of the tradeoffs involved here."),
        ("m2", True, "Another multi sentence answer with different emphasis entirely."),
    )
    out, mode, dis = asyncio.run(
        aggregate.aggregate("q", ans, caller=_judge, judge_alias="chair")
    )
    assert mode == "judge" and out == "Merged best answer." and "scope" in dis


def test_all_failed_raises():
    ans = _answers(("m1", False, None), ("m2", False, None))
    with pytest.raises(AllMembersFailed):
        asyncio.run(aggregate.aggregate("q", ans, caller=_judge, judge_alias="chair"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_aggregate.py -q`
Expected: FAIL — `council.aggregate` missing.

- [ ] **Step 3: Create `council/aggregate.py`**

```python
from __future__ import annotations

from collections import Counter

from council.errors import AllMembersFailed
from council.types import AsyncCaller, MemberAnswer

_JUDGE_PROMPT = (
    "You are the chair of a council. Below are {n} candidate answers to the same "
    "question. Produce the single best merged answer, then a final line starting with "
    "'DISAGREEMENTS:' noting where candidates differed (or 'none').\n\n"
    "Question:\n{prompt}\n\nCandidates:\n{candidates}"
)


def _looks_closed_form(answers: list[str]) -> bool:
    return all(len(a.strip().lower().rstrip(".!").split()) <= 3 for a in answers)


def _majority(answers: list[str]) -> str:
    norm = [a.strip().lower().rstrip(".!") for a in answers]
    return Counter(norm).most_common(1)[0][0]


async def aggregate(
    prompt: str, answers: list[MemberAnswer], *, caller: AsyncCaller, judge_alias: str
) -> tuple[str, str, str]:
    ok = [a.answer for a in answers if a.ok and a.answer is not None]
    if not ok:
        raise AllMembersFailed("every member abstained")
    if _looks_closed_form(ok):
        return _majority(ok), "vote", ""
    candidates = "\n".join(f"[{i + 1}] {a}" for i, a in enumerate(ok))
    merged = await caller(
        judge_alias, _JUDGE_PROMPT.format(n=len(ok), prompt=prompt, candidates=candidates)
    )
    disagreements = ""
    if "DISAGREEMENTS:" in merged:
        merged, _, disagreements = merged.partition("DISAGREEMENTS:")
    return merged.strip(), "judge", disagreements.strip()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_aggregate.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Lint & commit**

```bash
.venv/bin/ruff check .
git add council/aggregate.py tests/test_aggregate.py
git commit -m "feat: add adaptive aggregate (majority vote or judge synthesis)"
```

---

### Task 8: Orchestrator + live smoke script

**Files:**
- Create: `council/orchestrator.py`, `scripts/council-smoke.py`, `tests/test_orchestrator.py`

**Interfaces:**
- Consumes: registry, privacy, router, client, fanout, aggregate; all Task-1 types/errors.
- Produces: `class Orchestrator(members, caller, *, classifier_alias, chair_alias, default_member_aliases)` with async `ask(prompt, *, model=None, capability=None, sensitivity="sensitive") -> AskResult` and `council(prompt, *, members=None, sensitivity="sensitive") -> CouncilResult`; `orchestrator.build(config_path="proxy/config.yaml", *, base_url=DEFAULT_BASE_URL, api_key) -> Orchestrator`; the module constants from Global Constraints.

- [ ] **Step 1: Write the failing test**

Create `tests/test_orchestrator.py`:
```python
import asyncio

import pytest

from council.errors import PrivacyRefusal
from council.orchestrator import Orchestrator
from council.types import Member

GLM = Member("council/cerebras-glm-4.7", "A", ("reasoning", "general", "code"), 5, 5)
GROQ = Member("council/groq-gpt-oss-120b", "A", ("reasoning", "code", "general", "fast"), 4, 30)
CF = Member("council/cloudflare-llama-70b", "A", ("general", "fast"), 3, 10)
TIERB = Member("council/some-b", "B", ("general",), 2, 10)
ALL = [GLM, GROQ, CF, TIERB]


class Recorder:
    def __init__(self, answer="ANSWER"):
        self.answer = answer
        self.calls = []

    async def __call__(self, alias, prompt):
        self.calls.append((alias, prompt))
        if "DISAGREEMENTS" in prompt or "chair" in alias:
            return "Merged.\nDISAGREEMENTS: none"
        if "Classify" in prompt:
            return "reasoning"
        return self.answer


def _orch(caller):
    return Orchestrator(ALL, caller)


def test_ask_direct_model_skips_classify():
    rec = Recorder()
    r = asyncio.run(_orch(rec).ask("hi", model="council/groq-gpt-oss-120b"))
    assert r.model_used == "council/groq-gpt-oss-120b" and r.note == "direct"
    assert all("Classify" not in p for _, p in rec.calls)


def test_ask_auto_classifies_then_selects_strongest():
    rec = Recorder()
    r = asyncio.run(_orch(rec).ask("prove a theorem"))
    # classify -> "reasoning" -> strongest reasoning member is GLM (strength 5)
    assert r.capability == "reasoning" and r.model_used == "council/cerebras-glm-4.7"


def test_ask_sensitive_refuses_tier_b_model():
    with pytest.raises(PrivacyRefusal):
        asyncio.run(_orch(Recorder()).ask("hi", model="council/some-b", sensitivity="sensitive"))


def test_council_default_trio_and_judge():
    rec = Recorder()
    r = asyncio.run(_orch(rec).council("explain the tradeoffs in depth please"))
    assert {a.alias for a in r.per_member} == {
        "council/cerebras-glm-4.7",
        "council/groq-gpt-oss-120b",
        "council/cloudflare-llama-70b",
    }
    assert r.mode == "judge" and r.judge_used == "council/cerebras-glm-4.7"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_orchestrator.py -q`
Expected: FAIL — `council.orchestrator` missing.

- [ ] **Step 3: Create `council/orchestrator.py`**

```python
from __future__ import annotations

from council import aggregate as agg
from council import client, fanout, privacy, registry, router
from council.errors import NoEligibleMember, PrivacyRefusal
from council.types import AskResult, AsyncCaller, CouncilResult, Member

DEFAULT_BASE_URL = "http://127.0.0.1:4000/v1"
CLASSIFIER_ALIAS = "council/groq-llama-70b"
CHAIR_ALIAS = "council/cerebras-glm-4.7"
DEFAULT_MEMBER_ALIASES = (
    "council/cerebras-glm-4.7",
    "council/groq-gpt-oss-120b",
    "council/cloudflare-llama-70b",
)


class Orchestrator:
    def __init__(
        self,
        members: list[Member],
        caller: AsyncCaller,
        *,
        classifier_alias: str = CLASSIFIER_ALIAS,
        chair_alias: str = CHAIR_ALIAS,
        default_member_aliases: tuple[str, ...] = DEFAULT_MEMBER_ALIASES,
    ) -> None:
        self._members = members
        self._caller = caller
        self._classifier_alias = classifier_alias
        self._chair_alias = chair_alias
        self._default_member_aliases = default_member_aliases

    def _by_alias(self, alias: str) -> Member | None:
        return next((m for m in self._members if m.alias == alias), None)

    async def ask(
        self, prompt: str, *, model: str | None = None, capability: str | None = None,
        sensitivity: str = "sensitive",
    ) -> AskResult:
        privacy.scan_secrets(prompt)
        allowed = privacy.allowed_members(self._members, sensitivity)
        if model is not None:
            member = self._by_alias(model)
            if member is None or member not in allowed:
                raise PrivacyRefusal(
                    f"model {model} is not available for sensitivity={sensitivity}"
                )
            answer = await self._caller(member.alias, prompt)
            return AskResult(answer=answer, model_used=member.alias, capability=None, note="direct")
        if capability is None:
            capability = await router.classify(
                prompt, caller=self._caller, classifier_alias=self._classifier_alias
            )
            note = f"auto-routed: {capability}"
        else:
            note = f"routed: {capability}"
        member = router.select(allowed, capability)
        answer = await self._caller(member.alias, prompt)
        return AskResult(
            answer=answer, model_used=member.alias, capability=capability, note=note
        )

    async def council(
        self, prompt: str, *, members: tuple[str, ...] | None = None, sensitivity: str = "sensitive"
    ) -> CouncilResult:
        privacy.scan_secrets(prompt)
        allowed = privacy.allowed_members(self._members, sensitivity)
        wanted = members or self._default_member_aliases
        chosen = [m for m in allowed if m.alias in wanted]
        if not chosen:
            raise NoEligibleMember("no eligible council members for this sensitivity")
        answers = await fanout.fan_out(prompt, chosen, self._caller)
        merged, mode, disagreements = await agg.aggregate(
            prompt, answers, caller=self._caller, judge_alias=self._chair_alias
        )
        judge_used = self._chair_alias if mode == "judge" else None
        return CouncilResult(
            answer=merged, per_member=answers, disagreements=disagreements,
            judge_used=judge_used, mode=mode,
        )


def build(
    config_path: str = "proxy/config.yaml", *, base_url: str = DEFAULT_BASE_URL, api_key: str
) -> Orchestrator:
    members = registry.load_members(config_path)
    caller = client.make_caller(base_url, api_key)
    return Orchestrator(members, caller)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_orchestrator.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Create `scripts/council-smoke.py` (live dev smoke — not run in CI)**

```python
#!/usr/bin/env python3
"""Live smoke for the council orchestrator against the running proxy.

Requires the proxy up (bash scripts/run-proxy.sh) and LITELLM_MASTER_KEY in env
(set -a; source ~/.config/consilium/.env; set +a). Not part of the CI gate.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from council import orchestrator as orch  # noqa: E402


async def _main() -> int:
    key = os.environ.get("LITELLM_MASTER_KEY", "")
    if not key:
        print("ERROR: LITELLM_MASTER_KEY not set", file=sys.stderr)
        return 2
    o = orch.build(api_key=key)
    ask = await o.ask("In one word, is 17 prime? Answer yes or no.")
    print(f"[ask] model={ask.model_used} note={ask.note}\n  -> {ask.answer.strip()[:120]}")
    council = await o.council("Name one concrete risk of free-tier LLM routing and why.")
    print(f"[council] mode={council.mode} judge={council.judge_used}")
    for a in council.per_member:
        print(f"  {'ok ' if a.ok else 'ABS'} {a.alias}: {a.detail}")
    print(f"  -> {council.answer.strip()[:200]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
```

- [ ] **Step 6: Run the sub-wave 1a gate**

Run: `.venv/bin/ruff check . && .venv/bin/pytest -q`
Expected: ruff clean; all tests green (Phase-0 16/18 + Task1-8 new). No live calls.

- [ ] **Step 7: Commit**

```bash
git add council/orchestrator.py scripts/council-smoke.py tests/test_orchestrator.py
git commit -m "feat: add council orchestrator (ask + council) and live smoke script"
```

---

## Sub-wave 1b — MCP surface (Task 9) + protocol/close (Task 12)

### Task 9: MCP server (`ask` + `council` tools)

**Files:**
- Create: `consilium_mcp/server.py`, `tests/test_mcp_server.py`

**Interfaces:**
- Consumes: `orchestrator.build`, `Orchestrator` (Task 8); `AskResult`/`CouncilResult` (Task 1).
- Produces: FastMCP server `mcp` named `"consilium"` with tools `ask`/`council`; helpers `_load_master_key() -> str`, `_shape_ask(AskResult) -> dict`, `_shape_council(CouncilResult) -> dict`, `_get_orch() -> Orchestrator` (lazy, injectable via module global `_orch`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_mcp_server.py`:
```python
import pytest

from consilium_mcp import server
from council.types import AskResult, CouncilResult, MemberAnswer


def test_load_master_key_from_env(monkeypatch):
    monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-fromenv")
    assert server._load_master_key() == "sk-fromenv"


def test_load_master_key_from_file(monkeypatch, tmp_path):
    monkeypatch.delenv("LITELLM_MASTER_KEY", raising=False)
    home = tmp_path
    monkeypatch.setattr(server.Path, "home", staticmethod(lambda: home))
    target = home / ".config" / "consilium" / ".env"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("GROQ_API_KEY=x\nLITELLM_MASTER_KEY=sk-fromfile\n")
    assert server._load_master_key() == "sk-fromfile"


def test_load_master_key_missing_raises(monkeypatch, tmp_path):
    monkeypatch.delenv("LITELLM_MASTER_KEY", raising=False)
    monkeypatch.setattr(server.Path, "home", staticmethod(lambda: tmp_path))
    with pytest.raises(RuntimeError):
        server._load_master_key()


def test_shape_ask():
    r = AskResult(answer="a", model_used="council/x", capability="code", note="routed: code")
    assert server._shape_ask(r) == {
        "answer": "a", "model_used": "council/x", "capability": "code", "note": "routed: code",
    }


def test_shape_council():
    r = CouncilResult(
        answer="merged",
        per_member=[MemberAnswer("council/x", True, "hi", "ok")],
        disagreements="none",
        judge_used="council/x",
        mode="judge",
    )
    out = server._shape_council(r)
    assert out["answer"] == "merged" and out["mode"] == "judge"
    assert out["per_member"][0] == {"alias": "council/x", "ok": True, "detail": "ok", "answer": "hi"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_mcp_server.py -q`
Expected: FAIL — `consilium_mcp.server` missing.

- [ ] **Step 3: Create `consilium_mcp/server.py`**

```python
from __future__ import annotations

import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from council import orchestrator as orch
from council.types import AskResult, CouncilResult

mcp = FastMCP("consilium")
_orch: orch.Orchestrator | None = None


def _load_master_key() -> str:
    key = os.environ.get("LITELLM_MASTER_KEY")
    if key:
        return key
    env_file = Path.home() / ".config" / "consilium" / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("LITELLM_MASTER_KEY="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("LITELLM_MASTER_KEY not found in env or ~/.config/consilium/.env")


def _get_orch() -> orch.Orchestrator:
    global _orch
    if _orch is None:
        _orch = orch.build(api_key=_load_master_key())
    return _orch


def _shape_ask(r: AskResult) -> dict:
    return {
        "answer": r.answer,
        "model_used": r.model_used,
        "capability": r.capability,
        "note": r.note,
    }


def _shape_council(r: CouncilResult) -> dict:
    return {
        "answer": r.answer,
        "mode": r.mode,
        "judge_used": r.judge_used,
        "disagreements": r.disagreements,
        "per_member": [
            {"alias": a.alias, "ok": a.ok, "detail": a.detail, "answer": a.answer}
            for a in r.per_member
        ],
    }


@mcp.tool()
async def ask(
    prompt: str, model: str | None = None, capability: str | None = None,
    sensitivity: str = "sensitive",
) -> dict:
    """Ask one best-fit free model (auto-routed) or a specific model.

    sensitivity: "sensitive" (Tier-A only, default) or "public" (A+B).
    """
    return _shape_ask(
        await _get_orch().ask(prompt, model=model, capability=capability, sensitivity=sensitivity)
    )


@mcp.tool()
async def council(prompt: str, sensitivity: str = "sensitive") -> dict:
    """Convene the council: fan out to diverse free models and aggregate.

    sensitivity: "sensitive" (Tier-A only, default) or "public" (A+B).
    """
    return _shape_council(await _get_orch().council(prompt, sensitivity=sensitivity))


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_mcp_server.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Lint & commit**

```bash
.venv/bin/ruff check .
git add consilium_mcp/server.py tests/test_mcp_server.py
git commit -m "feat: add consilium MCP server exposing ask and council tools"
```

---

## Sub-wave 1c — Resilience: rate-limit fallback (Tasks 10–11)

These tasks MODIFY existing engine modules (`router.py`, `orchestrator.py`, `aggregate.py`) and their tests. Design basis: spec §13.

### Task 10: `ask` fallback across ranked members

**Files:**
- Modify: `council/router.py`, `council/orchestrator.py`
- Test: `tests/test_router.py`, `tests/test_orchestrator.py`

**Interfaces:**
- Produces: `router.rank(members, capability) -> list[Member]` (eligible, sorted by `(strength, rpm)` desc; raises `NoEligibleMember` if none); `select` becomes `rank(...)[0]`. `Orchestrator.ask` auto/capability paths iterate ranked candidates, falling back on `MemberCallError`, raising `AllMembersFailed` if all fail; direct `model=` does not fall back.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_router.py`:
```python
def test_rank_orders_by_strength_then_rpm():
    assert [m.alias for m in router.rank(MEMBERS, "general")] == ["strong", "fast"]


def test_rank_raises_when_no_capability():
    import pytest

    from council.errors import NoEligibleMember

    with pytest.raises(NoEligibleMember):
        router.rank(MEMBERS, "vision")
```

Add to `tests/test_orchestrator.py` — first extend the errors import line to:
```python
from council.errors import AllMembersFailed, MemberCallError, PrivacyRefusal
```
then append:
```python
def test_ask_auto_falls_back_on_rate_limit():
    class FB:
        async def __call__(self, alias, prompt):
            if "Classify" in prompt:
                return "reasoning"
            if alias == "council/cerebras-glm-4.7":
                raise MemberCallError(alias, "429 rate-limited")
            return "fallback answer"

    r = asyncio.run(_orch(FB()).ask("prove a theorem"))
    assert r.model_used == "council/groq-gpt-oss-120b"
    assert "429" in r.note


def test_ask_raises_all_members_failed_when_all_rate_limited():
    class AllFail:
        async def __call__(self, alias, prompt):
            if "Classify" in prompt:
                return "reasoning"
            raise MemberCallError(alias, "429 rate-limited")

    with pytest.raises(AllMembersFailed):
        asyncio.run(_orch(AllFail()).ask("x"))
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/pytest tests/test_router.py tests/test_orchestrator.py -q`
Expected: FAIL — `router.rank` missing; `ask` does not fall back.

- [ ] **Step 3: Add `rank` and re-express `select` in `council/router.py`**

Replace the `select` function at the end of `council/router.py` with:
```python
def rank(members: list[Member], capability: str) -> list[Member]:
    candidates = [m for m in members if capability in m.capabilities]
    if not candidates:
        raise NoEligibleMember(f"no member has capability '{capability}'")
    return sorted(candidates, key=lambda m: (m.strength, m.rpm), reverse=True)


def select(members: list[Member], capability: str) -> Member:
    return rank(members, capability)[0]
```

- [ ] **Step 4: Update `council/orchestrator.py` imports and `ask`**

Change the errors import to:
```python
from council.errors import AllMembersFailed, MemberCallError, NoEligibleMember, PrivacyRefusal
```
Replace the entire `ask` method with:
```python
    async def ask(
        self, prompt: str, *, model: str | None = None, capability: str | None = None,
        sensitivity: str = "sensitive",
    ) -> AskResult:
        privacy.scan_secrets(prompt)
        allowed = privacy.allowed_members(self._members, sensitivity)
        if model is not None:
            member = self._by_alias(model)
            if member is None or member not in allowed:
                raise PrivacyRefusal(
                    f"model {model} is not available for sensitivity={sensitivity}"
                )
            answer = await self._caller(member.alias, prompt)
            return AskResult(answer=answer, model_used=member.alias, capability=None, note="direct")
        auto = capability is None
        if auto:
            capability = await router.classify(
                prompt, caller=self._caller, classifier_alias=self._classifier_alias
            )
        errors: list[str] = []
        for member in router.rank(allowed, capability):
            try:
                answer = await self._caller(member.alias, prompt)
            except MemberCallError as exc:
                errors.append(f"{member.alias}[{exc.detail}]")
                continue
            trail = " -> ".join([*errors, member.alias])
            note = f"{'auto-routed' if auto else 'routed'}: {capability} -> {trail}"
            return AskResult(
                answer=answer, model_used=member.alias, capability=capability, note=note
            )
        raise AllMembersFailed(f"all '{capability}' members failed: {', '.join(errors)}")
```

- [ ] **Step 5: Run to verify pass**

Run: `.venv/bin/pytest tests/test_router.py tests/test_orchestrator.py -q`
Expected: PASS (router 7, orchestrator 6).

- [ ] **Step 6: Lint & commit**

```bash
.venv/bin/ruff check .
git add council/router.py council/orchestrator.py tests/test_router.py tests/test_orchestrator.py
git commit -m "feat: fall back across ranked members when ask hits a rate limit"
```

---

### Task 11: Judge fallback + best-single aggregation

**Files:**
- Modify: `council/aggregate.py`, `council/orchestrator.py`
- Test: `tests/test_aggregate.py` (rewrite), `tests/test_orchestrator.py` (unchanged — verifies via existing council test)

**Interfaces:**
- Produces: `aggregate.aggregate(prompt, answers, *, caller, judge_aliases: list[str]) -> tuple[str, str, str, str | None]` returning `(answer, mode, disagreements, judge_used)`, `mode ∈ {"vote","judge","best-single"}`. `Orchestrator.council` builds the judge order (chair first, then remaining chosen members by descending strength) via `_judge_order`.

- [ ] **Step 1: Rewrite the failing test `tests/test_aggregate.py`**

```python
import asyncio

import pytest

from council import aggregate
from council.errors import AllMembersFailed, MemberCallError
from council.types import MemberAnswer


def _answers(*pairs):
    return [MemberAnswer(a, ok=ok, answer=ans, detail="ok" if ok else "x") for a, ok, ans in pairs]


async def _judge(alias, prompt):
    return "Merged best answer.\nDISAGREEMENTS: candidate 2 differed on scope."


def test_vote_on_closed_form():
    ans = _answers(("m1", True, "Yes"), ("m2", True, "yes"), ("m3", True, "No"))
    out, mode, dis, judge = asyncio.run(
        aggregate.aggregate("q", ans, caller=_judge, judge_aliases=["chair"])
    )
    assert mode == "vote" and out == "yes" and dis == "" and judge is None


def test_judge_on_open_ended():
    ans = _answers(
        ("m1", True, "A long detailed explanation of the tradeoffs involved here."),
        ("m2", True, "Another multi sentence answer with different emphasis entirely."),
    )
    out, mode, dis, judge = asyncio.run(
        aggregate.aggregate("q", ans, caller=_judge, judge_aliases=["chair"])
    )
    assert mode == "judge" and out == "Merged best answer." and "scope" in dis and judge == "chair"


def test_judge_falls_back_to_next_judge():
    ans = _answers(
        ("m1", True, "A long detailed explanation of the tradeoffs involved here."),
        ("m2", True, "Another multi sentence answer with different emphasis entirely."),
    )

    async def caller(alias, prompt):
        if alias == "chair":
            raise MemberCallError("chair", "429 rate-limited")
        return "Backup merge.\nDISAGREEMENTS: none"

    out, mode, dis, judge = asyncio.run(
        aggregate.aggregate("q", ans, caller=caller, judge_aliases=["chair", "backup"])
    )
    assert mode == "judge" and judge == "backup" and out == "Backup merge."


def test_best_single_when_all_judges_fail():
    ans = _answers(
        ("m1", True, "short one"),
        ("m2", True, "A much longer and more substantive candidate answer here indeed."),
    )

    async def caller(alias, prompt):
        raise MemberCallError(alias, "429 rate-limited")

    out, mode, dis, judge = asyncio.run(
        aggregate.aggregate("q", ans, caller=caller, judge_aliases=["chair", "backup"])
    )
    assert mode == "best-single" and judge is None
    assert out == "A much longer and more substantive candidate answer here indeed."


def test_all_failed_raises():
    ans = _answers(("m1", False, None), ("m2", False, None))
    with pytest.raises(AllMembersFailed):
        asyncio.run(aggregate.aggregate("q", ans, caller=_judge, judge_aliases=["chair"]))
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_aggregate.py -q`
Expected: FAIL — `aggregate` still takes `judge_alias` and returns a 3-tuple.

- [ ] **Step 3: Rewrite `council/aggregate.py`**

```python
from __future__ import annotations

from collections import Counter

from council.errors import AllMembersFailed, MemberCallError
from council.types import AsyncCaller, MemberAnswer

_JUDGE_PROMPT = (
    "You are the chair of a council. Below are {n} candidate answers to the same "
    "question. Produce the single best merged answer, then a final line starting with "
    "'DISAGREEMENTS:' noting where candidates differed (or 'none').\n\n"
    "Question:\n{prompt}\n\nCandidates:\n{candidates}"
)


def _looks_closed_form(answers: list[str]) -> bool:
    return all(len(a.strip().lower().rstrip(".!").split()) <= 3 for a in answers)


def _majority(answers: list[str]) -> str:
    norm = [a.strip().lower().rstrip(".!") for a in answers]
    return Counter(norm).most_common(1)[0][0]


async def aggregate(
    prompt: str, answers: list[MemberAnswer], *, caller: AsyncCaller, judge_aliases: list[str]
) -> tuple[str, str, str, str | None]:
    ok = [a.answer for a in answers if a.ok and a.answer is not None]
    if not ok:
        raise AllMembersFailed("every member abstained")
    if _looks_closed_form(ok):
        return _majority(ok), "vote", "", None
    candidates = "\n".join(f"[{i + 1}] {a}" for i, a in enumerate(ok))
    for judge_alias in judge_aliases:
        try:
            merged = await caller(
                judge_alias,
                _JUDGE_PROMPT.format(n=len(ok), prompt=prompt, candidates=candidates),
            )
        except MemberCallError:
            continue
        disagreements = ""
        if "DISAGREEMENTS:" in merged:
            merged, _, disagreements = merged.partition("DISAGREEMENTS:")
        return merged.strip(), "judge", disagreements.strip(), judge_alias
    return max(ok, key=len), "best-single", "", None
```

- [ ] **Step 4: Update `council/orchestrator.py` `council` + add `_judge_order`**

Replace the entire `council` method with:
```python
    async def council(
        self, prompt: str, *, members: tuple[str, ...] | None = None, sensitivity: str = "sensitive"
    ) -> CouncilResult:
        privacy.scan_secrets(prompt)
        allowed = privacy.allowed_members(self._members, sensitivity)
        wanted = members or self._default_member_aliases
        chosen = [m for m in allowed if m.alias in wanted]
        if not chosen:
            raise NoEligibleMember("no eligible council members for this sensitivity")
        answers = await fanout.fan_out(prompt, chosen, self._caller)
        merged, mode, disagreements, judge_used = await agg.aggregate(
            prompt, answers, caller=self._caller, judge_aliases=self._judge_order(chosen)
        )
        return CouncilResult(
            answer=merged, per_member=answers, disagreements=disagreements,
            judge_used=judge_used, mode=mode,
        )

    def _judge_order(self, chosen: list[Member]) -> list[str]:
        rest = sorted(
            (m for m in chosen if m.alias != self._chair_alias),
            key=lambda m: m.strength, reverse=True,
        )
        return [self._chair_alias, *(m.alias for m in rest)]
```

- [ ] **Step 5: Run to verify pass**

Run: `.venv/bin/pytest tests/test_aggregate.py tests/test_orchestrator.py -q`
Expected: PASS (aggregate 5; orchestrator's existing council test still green — chair is first judge and succeeds → `mode="judge"`, `judge_used="council/cerebras-glm-4.7"`).

- [ ] **Step 6: Full gate, lint & commit**

```bash
.venv/bin/ruff check . && .venv/bin/pytest -q
git add council/aggregate.py council/orchestrator.py tests/test_aggregate.py
git commit -m "feat: fall back across judges and to best-single answer under rate limits"
```

---

## Sub-wave 1b — close (Task 12)

### Task 12: Usage protocol, README, registration, final gate

**Files:**
- Create: `docs/usage-rule.md`, `council/README.md`
- Modify: `CLAUDE.md` (structure note re: `consilium_mcp/`)

**Interfaces:**
- Consumes: everything above.
- Produces: operator + protocol docs; final green gate.

- [ ] **Step 1: Create `docs/usage-rule.md`**

````markdown
# Consilium usage rule — append to `~/.claude/CLAUDE.md`

Paste the block below into `~/.claude/CLAUDE.md` so every project knows when/how to
consult the council.

```markdown
## Free-LLM council (consilium MCP)

A user-scope MCP server exposes two tools backed by a privacy-gated pool of free
Tier-A models (proxy at 127.0.0.1:4000). The council is a **second opinion, not the
driver** — you (Claude) remain the primary reasoner.

- `ask(prompt, model?, capability?, sensitivity?)` — one best-fit model. Default
  auto-routes (classifies the task). Use for a quick routed second opinion, a cheap
  bulk step, or a strength-specific call (pass `capability` = reasoning|code|fast|general,
  or `model` for a specific member).
- `council(prompt, sensitivity?)` — fan out to diverse models + aggregate. Use for
  high-stakes cross-checks where diverse errors matter (costs more free-tier RPD).
- **Privacy:** always set `sensitivity`. Default `sensitive` (Tier-A only). Use
  `public` only for generic/published questions. **Never** send secrets/.env/credentials
  to any free tier — the gate refuses obvious secrets, but strip them yourself first.
- **Rate hygiene:** prefer `ask`; reserve `council` for when a cross-check is worth it.
- **Rate limits degrade gracefully:** if a free model is rate-limited, `ask` falls back
  to the next-best model automatically, and `council` drops the limited voter (and falls
  back to another judge, or the best single answer). A `note`/`mode` field records what
  happened. Only if *every* eligible model is exhausted does a call error out.
```

## Registering the MCP server (once, global)

Requires the proxy running and keys in `~/.config/consilium/.env`.

```bash
claude mcp add --scope user consilium -- \
  /opt/claude-projects/llm-consilium/.venv/bin/python \
  /opt/claude-projects/llm-consilium/consilium_mcp/server.py
```
The server reads `LITELLM_MASTER_KEY` from `~/.config/consilium/.env`; it needs the
proxy up on 127.0.0.1:4000.
````

- [ ] **Step 2: Create `council/README.md`**

````markdown
# Council orchestrator (Phase 1)

`ask` (one best-fit model) and `council` (fan-out + adaptive aggregate) over the
Phase-0 proxy, exposed as the `consilium` MCP server.

## Live smoke (proxy must be up)
```bash
bash scripts/run-proxy.sh            # terminal 1
# terminal 2:
set -a; source ~/.config/consilium/.env; set +a
.venv/bin/python scripts/council-smoke.py
```

## Register the MCP tools
See `docs/usage-rule.md` for the `claude mcp add --scope user` command and the
`~/.claude/CLAUDE.md` protocol block.
````

- [ ] **Step 3: Update `CLAUDE.md` (structure note + phase reconciliation)**

3a. In `CLAUDE.md`, find the structure-diagram line:
```
├── mcp/                         # user-scope MCP server exposing the `council` tool
```
Replace with:
```
├── consilium_mcp/               # user-scope MCP server (not `mcp/` — that shadows the SDK)
```

3b. Reconcile the phase numbering (spec §14). In `CLAUDE.md`'s `## Status` section, replace the "Phase 0 not started…" text with a current phase map:
```
**Phase 0 (compute) and Phase 1 (council + MCP) complete.** Phase map:
- Phase 0 — LiteLLM proxy + 3 Tier-A providers (Cerebras/Groq/Cloudflare). Done.
- Phase 1 — council orchestrator (`ask`/`council`) + user-scope MCP + usage protocol +
  rate-limit fallback. Done (sub-waves 1a engine · 1b MCP · 1c resilience).
- Phase 2 — deployment hardening: systemd always-on, RPD/quota telemetry + rotation,
  backoff, additional providers (incl. Tier-B under the gate). Not started.
```
(The originally-separate SUPERPROMPT Phase 1/Phase 2 were merged into this Phase 1;
old "Phase 3" is now "Phase 2".)

- [ ] **Step 4: Run the full CI-safe gate**

Run: `.venv/bin/ruff check . && .venv/bin/pytest -q`
Expected: ruff `All checks passed!`; pytest all green (Phase-0 + Phase-1 unit tests).

- [ ] **Step 5: Commit**

```bash
git add docs/usage-rule.md council/README.md CLAUDE.md
git commit -m "docs: add council usage protocol, README, and MCP registration"
```

---

## Self-Review

**Spec coverage (against `2026-07-13-phase-1-council-orchestrator-mcp-design.md`):**
- §3 components → `types/errors` (T1), `registry` (T2), `privacy` (T3), `client` (T4), `router` (T5), `fanout` (T6), `aggregate` (T7), `orchestrator`+smoke (T8), `consilium_mcp/server` (T9). ✓
- §4 data types & interfaces → dataclasses + `AsyncCaller` (T1); every listed function signature appears in its task's Interfaces block with matching names. ✓
- §5 registry & capability tags → config edit + `load_members` (T2); starter strength/capabilities match the spec table. ✓
- §6 `ask`/`council` behavior (direct/capability/auto; fan-out; adaptive vote/judge; default trio; chair) → T5/T6/T7/T8, asserted in `test_orchestrator.py`. ✓
- §7 privacy gate (sensitivity default sensitive; tier filter; secret-scan refusal) → T3, and enforced in orchestrator (T8) with `test_ask_sensitive_refuses_tier_b_model`. ✓
- §8 MCP server + usage protocol → T9 (`ask`/`council` tools, master-key loading) + T10 (`docs/usage-rule.md`, `claude mcp add`). ✓
- §9 error handling (typed errors; dead member abstains, never crashes) → errors (T1), fanout abstain (T6), surfaced results (T8). ✓
- §10 testing (CI-safe fakes; live smoke separate) → every task has CI-safe unit tests; live smoke in T8; gate in T8/T10. ✓
- §11 acceptance → covered across T8 (ask/council/gate) and T10 (registration doc + final gate). ✓
- §13 resilience (ask fallback via `router.rank`; judge fallback + best-single; direct `model=` no fallback) → T10 (`test_ask_auto_falls_back...`) + T11 (`test_judge_falls_back...`, `test_best_single...`). ✓

**Placeholder scan:** No TBD/TODO; every code step shows full content; version specifiers are bounded ranges. ✓

**Type consistency:** `Member`/`MemberAnswer`/`AskResult`/`CouncilResult`/`AsyncCaller` and functions `load_members`, `scan_secrets`, `allowed_members`, `complete`, `make_caller`, `classify`, `select`, `fan_out`, `aggregate`, `Orchestrator.ask/council`, `build`, `_load_master_key`, `_shape_ask`, `_shape_council` are named identically in every task that defines or consumes them. Constants (`CLASSIFIER_ALIAS`, `CHAIR_ALIAS`, `DEFAULT_MEMBER_ALIASES`, `DEFAULT_BASE_URL`) match Global Constraints. The 5 aliases match Phase-0 config and `test_registry.py`. ✓
