# Phase 2c — Providers + Rate-limit Robustness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Grow the council to 13 members across 7 provider families with per-capability dossiers, a dynamic (capability-aware, adaptive-size, vendor-diverse) roster with manual override, key-presence activation, and LiteLLM-native rate-limit failover — all under the unchanged, non-bypassable privacy gate.

**Architecture:** Replace the flat `capabilities`+`strength` on `Member` with a `scores: dict[str,int]` map plus `provider_family`, exposing `capabilities`/`strength` as derived read-only properties so only construction sites change. Router ranks by the requested capability's score; a new `compose_council` picks top-K with vendor diversity; the orchestrator's `council` gains manual-roster and adaptive-size paths. Key-presence activation reads `~/.config/consilium/.env` (the MCP process holds only the master key, so it cannot rely on `os.environ` for provider keys). LiteLLM-native `retry_policy`/`fallbacks`/`cooldown` complement (do not replace) the 2b usage-store daily rotation.

**Tech Stack:** Python 3.10, pyyaml, asyncio/httpx, pytest, ruff, LiteLLM proxy, MCP Python SDK (FastMCP).

## Global Constraints

- **Privacy gate is a hard rule.** `sensitive` → Tier-A members only; Tier-B reachable only by `public`. Holds on every path including manual roster: a manually-requested Tier-B member on a `sensitive` prompt is dropped, never called (recorded in a note).
- **Fallbacks never cross tiers.** A Tier-A model must never fall back to a Tier-B model.
- **Secrets only in `~/.config/consilium/.env`** (chmod 600). Never in code, git, logs, or memory. Config references keys via `os.environ/NAME`.
- **Tier verdicts:** GitHub Models = A; Mistral, SambaNova, NVIDIA NIM = B. Tier follows the inference provider.
- **NVIDIA has no key this phase** — its two aliases stay in config but dormant via key-presence activation; live smoke skips them.
- Python 3.10+. `ruff check .` clean + `pytest -q` green is the hard gate per task. Commits: English imperative, **no `Co-Authored-By`**. Never force-push / `--no-verify`. Work on branch `phase-2c-providers` (already created).
- Provisional model IDs/limits **drift** — Task 9 validates them live and corrects config.

## File map

- `council/types.py` — `Member` gains `scores`, `provider_family`; `capabilities`/`strength` become properties. `CouncilResult` gains `note`.
- `council/registry.py` — parse `scores` (+ legacy synth), derive `provider_family`, key-presence filter, `available_env_keys()`.
- `council/router.py` — `rank`/`select` sort by capability score.
- `council/compose.py` — NEW: `compose_council` (vendor-diverse top-K) + `adaptive_k`.
- `council/orchestrator.py` — `council` rewrite (manual/auto/size, notes); `build` wires key-presence.
- `consilium_mcp/server.py` — `council(members, size)` + docstrings; `_shape_council` adds `note`; `ask` docstring.
- `proxy/config.yaml` — migrate 5 to `scores`; +8 aliases; `router_settings` retry/fallbacks/cooldown.
- `scripts/run-proxy.sh` — non-fatal notice of active/dormant optional providers.
- `scripts/council-smoke.py` — live validation of new aliases + tier isolation.
- `docs/usage-rule.md` — document `members`/`size`.
- Tests across `tests/`.

---

### Task 1: Member dossier type + registry parsing + migrate existing config & tests

**Files:**
- Modify: `council/types.py`
- Modify: `council/registry.py`
- Modify: `proxy/config.yaml` (existing 5 entries only)
- Modify: `tests/test_types.py`, `tests/test_registry.py`, `tests/test_router.py`, `tests/test_orchestrator.py`, `tests/test_privacy.py`, `tests/test_fanout.py`, `tests/test_usage.py`

**Interfaces:**
- Produces: `Member(alias: str, privacy_tier: str, scores: dict[str,int], rpm: int, provider_family: str = "", rpd: int|None = None, tpd: int|None = None)` with read-only properties `capabilities -> tuple[str,...]` (= `tuple(scores)`) and `strength -> int` (= `max(scores.values())` or 1). `registry.load_members(config_path) -> list[Member]` parses `model_info.scores` (map cap→int); if `scores` absent, synthesizes from legacy `strength`+`capabilities`; `provider_family` from `model_info.provider_family` else derived from the litellm `model` string.

- [ ] **Step 1: Rewrite `Member` in `council/types.py`**

```python
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

# (alias, prompt) -> answer text
AsyncCaller = Callable[[str, str], Awaitable[str]]


@dataclass(frozen=True)
class Member:
    alias: str
    privacy_tier: str
    scores: dict[str, int]
    rpm: int
    provider_family: str = ""
    rpd: int | None = None
    tpd: int | None = None

    @property
    def capabilities(self) -> tuple[str, ...]:
        return tuple(self.scores)

    @property
    def strength(self) -> int:
        return max(self.scores.values()) if self.scores else 1


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
    note: str = ""
```

(`field` import is unused for now; drop it — keep imports minimal: `from dataclasses import dataclass`.)

- [ ] **Step 2: Rewrite `tests/test_types.py` construction to the new signature**

Replace the `Member(...)` on line 16 and any `.capabilities`/`.strength` assertions:

```python
def test_member_scores_and_derived_props():
    m = Member(alias="a", privacy_tier="A", scores={"general": 3, "code": 4}, rpm=5)
    assert m.capabilities == ("general", "code")
    assert m.strength == 4
    assert m.provider_family == "" and m.rpd is None and m.tpd is None
```

(Keep any other existing tests in the file; only fix constructions/assertions that used `capabilities=`/`strength=` kwargs.)

- [ ] **Step 3: Run it — expect failure (Member has no `scores`)**

Run: `.venv/bin/pytest tests/test_types.py -q`
Expected: FAIL (TypeError / AttributeError) until types.py is saved — after Step 1 it PASSES. If green already, continue.

- [ ] **Step 4: Rewrite `council/registry.py` to parse `scores`, legacy synth, and derive family**

```python
from __future__ import annotations

from pathlib import Path

import yaml

from council.types import Member


def _derive_family(model: str) -> str:
    if model.startswith("openai/@cf/"):  # Cloudflare Workers AI shim
        return "cloudflare"
    return model.split("/", 1)[0] if "/" in model else model


def _scores(info: dict) -> dict[str, int]:
    raw = info.get("scores")
    if isinstance(raw, dict) and raw:
        return {str(k): int(v) for k, v in raw.items()}
    # Legacy fallback: flat strength + capabilities list.
    strength = int(info.get("strength", 1))
    caps = info.get("capabilities", ["general"])
    return {str(c): strength for c in caps}


def load_members(config_path: str | Path) -> list[Member]:
    data = yaml.safe_load(Path(config_path).read_text())
    members: list[Member] = []
    for entry in data.get("model_list", []):
        info = entry.get("model_info") or {}
        params = entry.get("litellm_params") or {}
        rpd = info.get("rpd")
        tpd = info.get("tpd")
        family = info.get("provider_family") or _derive_family(str(params.get("model", "")))
        members.append(
            Member(
                alias=entry["model_name"],
                privacy_tier=info.get("privacy_tier", "B"),
                scores=_scores(info),
                rpm=int(params.get("rpm", 10)),
                provider_family=family,
                rpd=int(rpd) if rpd is not None else None,
                tpd=int(tpd) if tpd is not None else None,
            )
        )
    return members
```

- [ ] **Step 5: Migrate the 5 existing entries in `proxy/config.yaml` to `scores`**

For each existing entry replace `strength: N` + `capabilities: [a, b, c]` with a `scores:` map (assign the old strength to the first/strongest capability and reasonable values to the rest). Keep `privacy_tier`, `rpd`/`tpd`, and `litellm_params` unchanged. Concretely:

```yaml
  - model_name: council/cerebras-glm-4.7
    litellm_params:
      model: cerebras/zai-glm-4.7
      api_key: os.environ/CEREBRAS_API_KEY
      rpm: 5
    model_info:
      privacy_tier: A
      scores: {reasoning: 5, code: 4, general: 4}
      tpd: 1000000
  - model_name: council/cerebras-gpt-oss-120b
    litellm_params:
      model: cerebras/gpt-oss-120b
      api_key: os.environ/CEREBRAS_API_KEY
      rpm: 5
    model_info:
      privacy_tier: A
      scores: {reasoning: 4, code: 4, general: 4}
      tpd: 1000000
  - model_name: council/groq-llama-70b
    litellm_params:
      model: groq/llama-3.3-70b-versatile
      api_key: os.environ/GROQ_API_KEY
      rpm: 30
    model_info:
      privacy_tier: A
      scores: {general: 3, fast: 3, code: 3}
      rpd: 1000
  - model_name: council/groq-gpt-oss-120b
    litellm_params:
      model: groq/openai/gpt-oss-120b
      api_key: os.environ/GROQ_API_KEY
      rpm: 30
    model_info:
      privacy_tier: A
      scores: {reasoning: 4, code: 4, general: 4, fast: 4}
      rpd: 1000
  - model_name: council/cloudflare-llama-70b
    litellm_params:
      model: openai/@cf/meta/llama-3.3-70b-instruct-fp8-fast
      api_base: os.environ/CLOUDFLARE_API_BASE
      api_key: os.environ/CLOUDFLARE_API_TOKEN
    model_info:
      privacy_tier: A
      scores: {general: 3, fast: 3}
      tpd: 10000
```

Keep the file's existing top comments and `router_settings`/`general_settings`.

- [ ] **Step 6: Update `tests/test_registry.py` for scores/family (still 5 members)**

```python
def test_capabilities_and_scores_parsed():
    glm = _members()["council/cerebras-glm-4.7"]
    assert glm.privacy_tier == "A"
    assert glm.scores["reasoning"] == 5
    assert glm.strength == 5
    assert "reasoning" in glm.capabilities


def test_provider_family_derived():
    m = _members()
    assert m["council/cerebras-glm-4.7"].provider_family == "cerebras"
    assert m["council/groq-gpt-oss-120b"].provider_family == "groq"
    assert m["council/cloudflare-llama-70b"].provider_family == "cloudflare"


def test_legacy_strength_capabilities_synthesized(tmp_path):
    cfg = tmp_path / "legacy.yaml"
    cfg.write_text(
        "model_list:\n"
        "  - model_name: council/legacy\n"
        "    litellm_params: {model: groq/x, rpm: 7}\n"
        "    model_info: {privacy_tier: A, strength: 4, capabilities: [reasoning, code]}\n"
    )
    m = {x.alias: x for x in registry.load_members(cfg)}["council/legacy"]
    assert m.scores == {"reasoning": 4, "code": 4}
    assert m.strength == 4 and m.provider_family == "groq"
```

Keep `test_daily_caps_parsed` and `test_rpm_defaults_when_absent` as-is (they use rpd/tpd/rpm, unchanged). Update `test_capabilities_and_strength_parsed` to the new `test_capabilities_and_scores_parsed` above (delete the old one). Leave `test_loads_all_five_members` unchanged — still 5 in this task.

- [ ] **Step 7: Migrate every remaining `Member(...)` construction in tests**

Transformation rule for `Member(ALIAS, TIER, CAPS_TUPLE, STRENGTH, RPM, **kw)` →
`Member(ALIAS, TIER, {c: STRENGTH for c in CAPS_TUPLE}, RPM, "FAM", **kw)` where `FAM` is a short unique family tag. Apply to:

`tests/test_orchestrator.py` module constants and inline members:
```python
GLM = Member("council/cerebras-glm-4.7", "A", {"reasoning": 5, "general": 5, "code": 5}, 5, "cerebras")
GROQ = Member("council/groq-gpt-oss-120b", "A", {"reasoning": 4, "code": 4, "general": 4, "fast": 4}, 30, "groq")
CF = Member("council/cloudflare-llama-70b", "A", {"general": 3, "fast": 3}, 10, "cloudflare")
TIERB = Member("council/some-b", "B", {"general": 2}, 10, "someb")
```
- line 90: `tierb_classifier = Member("council/tierb-classifier", "B", {"general": 2}, 99, "tierbc")`
- line 122: `Member("council/cerebras-glm-4.7", "A", {"reasoning": 5}, 5, "cerebras", tpd=1000000)`
- lines 133-135: reuse the constants' scores/family, e.g.
  `Member(GLM.alias, "A", GLM.scores, 5, "cerebras", tpd=1)`, likewise GROQ→`"groq"`, CF→`"cloudflare"`.

`tests/test_router.py`:
```python
STRONG = Member("strong", "A", {"reasoning": 5, "general": 5}, 5, "s")
FAST = Member("fast", "A", {"fast": 3, "general": 3}, 30, "f")
CODER = Member("coder", "A", {"code": 4}, 10, "c")
```
- lines 20-21: `a = Member("a", "A", {"general": 3}, 5, "a")`, `b = Member("b", "A", {"general": 3}, 30, "b")`

`tests/test_privacy.py`:
```python
A = Member("a", "A", {"general": 3}, 5, "a")
B = Member("b", "B", {"general": 3}, 5, "b")
```

`tests/test_fanout.py`:
```python
M1 = Member("m1", "A", {"general": 3}, 5, "m1")
M2 = Member("m2", "A", {"general": 3}, 5, "m2")
```

`tests/test_usage.py`:
```python
CAPPED_REQ = Member("r", "A", {"general": 3}, 5, "r", rpd=2, tpd=None)
CAPPED_TOK = Member("t", "A", {"general": 3}, 5, "t", rpd=None, tpd=100)
UNCAPPED = Member("u", "A", {"general": 3}, 5, "u")
```

- [ ] **Step 8: Run the full suite green**

Run: `.venv/bin/ruff check . && .venv/bin/pytest -q`
Expected: PASS (all existing tests + new registry/type tests). Fix any missed construction site until green.

- [ ] **Step 9: Commit**

```bash
git add council/types.py council/registry.py proxy/config.yaml tests/
git commit -m "feat(2c): per-capability dossier on Member + registry scores/family parsing"
```

---

### Task 2: Add the 8 new provider aliases to config

**Files:**
- Modify: `proxy/config.yaml`
- Modify: `tests/test_registry.py`

**Interfaces:**
- Consumes: `registry.load_members` (Task 1).
- Produces: config with 13 members (7 Tier-A, 6 Tier-B). IDs provisional — Task 9 validates live.

- [ ] **Step 1: Update `test_loads_all_five_members` to the full 13-member set (rename it)**

```python
def test_loads_all_thirteen_members():
    assert set(_members()) == {
        "council/cerebras-glm-4.7", "council/cerebras-gpt-oss-120b",
        "council/groq-llama-70b", "council/groq-gpt-oss-120b",
        "council/cloudflare-llama-70b",
        "council/github-gpt-4.1", "council/github-o4-mini",
        "council/mistral-large", "council/mistral-codestral",
        "council/sambanova-llama-405b", "council/sambanova-llama-70b",
        "council/nvidia-deepseek-r1", "council/nvidia-llama-70b",
    }


def test_tier_b_providers_tagged_b():
    m = _members()
    for alias in ["council/mistral-large", "council/sambanova-llama-405b",
                  "council/nvidia-deepseek-r1"]:
        assert m[alias].privacy_tier == "B"
    assert m["council/github-gpt-4.1"].privacy_tier == "A"
```

- [ ] **Step 2: Run — expect failure**

Run: `.venv/bin/pytest tests/test_registry.py::test_loads_all_thirteen_members -q`
Expected: FAIL (only 5 members present).

- [ ] **Step 3: Append the 8 new entries to `proxy/config.yaml` `model_list`**

```yaml
  # --- Phase 2c additions. Model IDs provisional; validated live in Task 9. ---
  # GitHub Models — documented no-train => Tier A (GPT-class safe tier win).
  - model_name: council/github-gpt-4.1
    litellm_params:
      model: github/gpt-4.1
      api_key: os.environ/GITHUB_API_KEY
      rpm: 10
    model_info:
      privacy_tier: A
      scores: {general: 5, code: 5, reasoning: 4}
      rpd: 50
  - model_name: council/github-o4-mini
    litellm_params:
      model: github/o4-mini
      api_key: os.environ/GITHUB_API_KEY
      rpm: 10
    model_info:
      privacy_tier: A
      scores: {reasoning: 5, fast: 4, code: 4, general: 3}
      rpd: 50
  # Tier B — free tier trains/retains or undocumented => public prompts only.
  - model_name: council/mistral-large
    litellm_params:
      model: mistral/mistral-large-latest
      api_key: os.environ/MISTRAL_API_KEY
      rpm: 6
    model_info:
      privacy_tier: B
      scores: {reasoning: 4, general: 4, code: 3}
  - model_name: council/mistral-codestral
    litellm_params:
      model: mistral/codestral-latest
      api_key: os.environ/MISTRAL_API_KEY
      rpm: 6
    model_info:
      privacy_tier: B
      scores: {code: 5, fast: 4, general: 3}
  - model_name: council/sambanova-llama-405b
    litellm_params:
      model: sambanova/Meta-Llama-3.1-405B-Instruct
      api_key: os.environ/SAMBANOVA_API_KEY
      rpm: 10
    model_info:
      privacy_tier: B
      scores: {reasoning: 4, general: 4, code: 3}
  - model_name: council/sambanova-llama-70b
    litellm_params:
      model: sambanova/Meta-Llama-3.3-70B-Instruct
      api_key: os.environ/SAMBANOVA_API_KEY
      rpm: 10
    model_info:
      privacy_tier: B
      scores: {fast: 5, general: 3, code: 3}
  # NVIDIA NIM — no key this phase; key-presence activation keeps these dormant.
  - model_name: council/nvidia-deepseek-r1
    litellm_params:
      model: nvidia_nim/deepseek-ai/deepseek-r1
      api_key: os.environ/NVIDIA_NIM_API_KEY
      rpm: 10
    model_info:
      privacy_tier: B
      scores: {reasoning: 5, general: 3}
  - model_name: council/nvidia-llama-70b
    litellm_params:
      model: nvidia_nim/meta/llama-3.3-70b-instruct
      api_key: os.environ/NVIDIA_NIM_API_KEY
      rpm: 10
    model_info:
      privacy_tier: B
      scores: {general: 3, code: 3, fast: 4}
```

- [ ] **Step 4: Run — expect pass**

Run: `.venv/bin/ruff check . && .venv/bin/pytest tests/test_registry.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add proxy/config.yaml tests/test_registry.py
git commit -m "feat(2c): add GitHub Models (Tier A) + Mistral/SambaNova/NVIDIA (Tier B) aliases"
```

---

### Task 3: Key-presence activation

**Files:**
- Modify: `council/registry.py`
- Modify: `council/orchestrator.py` (build wiring)
- Modify: `tests/test_registry.py`

**Interfaces:**
- Produces:
  - `registry.available_env_keys(env_file: str|Path = ~/.config/consilium/.env) -> set[str]` — names present & non-empty in `os.environ` ∪ the env file.
  - `registry.load_members(config_path, *, available_keys: set[str]|None = None)` — when `available_keys` is not None, drop any member referencing an `os.environ/NAME` not in the set. `None` (default) = no filtering (hermetic).
- Consumes: `orchestrator.build` now filters by `available_env_keys()`.

- [ ] **Step 1: Write failing tests in `tests/test_registry.py`**

```python
def test_available_env_keys_reads_process_and_file(tmp_path, monkeypatch):
    monkeypatch.setenv("FOO_KEY", "x")
    monkeypatch.delenv("BAR_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text("BAR_KEY=y\nEMPTY_KEY=\n# comment\n")
    keys = registry.available_env_keys(env)
    assert "FOO_KEY" in keys and "BAR_KEY" in keys
    assert "EMPTY_KEY" not in keys


def test_load_members_filters_missing_keys():
    # Only Cerebras/Groq keys "available" -> Cloudflare + all Tier-B drop out.
    keys = {"CEREBRAS_API_KEY", "GROQ_API_KEY"}
    aliases = {m.alias for m in registry.load_members(CONFIG, available_keys=keys)}
    assert "council/cerebras-glm-4.7" in aliases
    assert "council/groq-llama-70b" in aliases
    assert "council/cloudflare-llama-70b" not in aliases  # needs CLOUDFLARE_* 
    assert "council/mistral-large" not in aliases
    assert "council/nvidia-deepseek-r1" not in aliases


def test_load_members_no_filter_returns_all():
    assert len(registry.load_members(CONFIG)) == 13
```

- [ ] **Step 2: Run — expect failure**

Run: `.venv/bin/pytest tests/test_registry.py::test_load_members_filters_missing_keys -q`
Expected: FAIL (`available_env_keys` / `available_keys` not implemented).

- [ ] **Step 3: Implement in `council/registry.py`**

Add near the top:
```python
import os
import re

_ENV_REF = re.compile(r"os\.environ/([A-Za-z_][A-Za-z0-9_]*)")
DEFAULT_ENV_FILE = Path.home() / ".config" / "consilium" / ".env"


def available_env_keys(env_file: str | Path = DEFAULT_ENV_FILE) -> set[str]:
    keys = {k for k, v in os.environ.items() if v}
    path = Path(env_file)
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, _, value = line.partition("=")
            if value.strip():
                keys.add(name.strip())
    return keys


def _required_env(params: dict) -> set[str]:
    names: set[str] = set()
    for value in params.values():
        if isinstance(value, str):
            names.update(_ENV_REF.findall(value))
    return names
```

In `load_members`, add the parameter and filter:
```python
def load_members(
    config_path: str | Path, *, available_keys: set[str] | None = None
) -> list[Member]:
    data = yaml.safe_load(Path(config_path).read_text())
    members: list[Member] = []
    for entry in data.get("model_list", []):
        info = entry.get("model_info") or {}
        params = entry.get("litellm_params") or {}
        if available_keys is not None and not _required_env(params) <= available_keys:
            continue  # key-presence activation: a member with a missing key is dormant
        rpd = info.get("rpd")
        tpd = info.get("tpd")
        family = info.get("provider_family") or _derive_family(str(params.get("model", "")))
        members.append(
            Member(
                alias=entry["model_name"],
                privacy_tier=info.get("privacy_tier", "B"),
                scores=_scores(info),
                rpm=int(params.get("rpm", 10)),
                provider_family=family,
                rpd=int(rpd) if rpd is not None else None,
                tpd=int(tpd) if tpd is not None else None,
            )
        )
    return members
```

- [ ] **Step 4: Wire `orchestrator.build` to filter by present keys**

In `council/orchestrator.py` `build(...)`:
```python
def build(
    config_path: str = "proxy/config.yaml", *, base_url: str = DEFAULT_BASE_URL, api_key: str
) -> Orchestrator:
    members = registry.load_members(config_path, available_keys=registry.available_env_keys())
    store = usage.UsageStore()
    caller = client.make_caller(base_url, api_key, recorder=store.record)
    return Orchestrator(members, caller, store=store)
```

- [ ] **Step 5: Run — expect pass**

Run: `.venv/bin/ruff check . && .venv/bin/pytest tests/test_registry.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add council/registry.py council/orchestrator.py tests/test_registry.py
git commit -m "feat(2c): key-presence activation (dormant providers without keys)"
```

---

### Task 4: Router ranks by capability score

**Files:**
- Modify: `council/router.py`
- Modify: `tests/test_router.py`

**Interfaces:**
- Produces: `rank(members, capability)` sorts eligible (`capability in m.scores`) by `m.scores[capability]` desc, then `m.rpm` desc; raises `NoEligibleMember` if none. `select` unchanged (`rank[0]`).

- [ ] **Step 1: Add failing test — a specialist beats a stronger generalist on its axis**

Append to `tests/test_router.py`:
```python
def test_rank_uses_capability_score_not_overall():
    generalist = Member("gen", "A", {"general": 5, "code": 2}, 10, "g")
    specialist = Member("spec", "A", {"code": 5, "general": 2}, 10, "s")
    assert router.select([generalist, specialist], "code") is specialist
    assert router.select([generalist, specialist], "general") is generalist
```

- [ ] **Step 2: Run — expect failure**

Run: `.venv/bin/pytest tests/test_router.py::test_rank_uses_capability_score_not_overall -q`
Expected: FAIL (current `rank` sorts by `m.strength`, so specialist and generalist tie on strength 5 and order is input-order).

- [ ] **Step 3: Update `rank` in `council/router.py`**

```python
def rank(members: list[Member], capability: str) -> list[Member]:
    candidates = [m for m in members if capability in m.scores]
    if not candidates:
        raise NoEligibleMember(f"no member has capability '{capability}'")
    return sorted(candidates, key=lambda m: (m.scores[capability], m.rpm), reverse=True)
```

- [ ] **Step 4: Run — expect pass (whole router suite)**

Run: `.venv/bin/ruff check . && .venv/bin/pytest tests/test_router.py -q`
Expected: PASS (`test_rank_orders_by_strength_then_rpm` still holds: on "general", STRONG=5 beats FAST=3).

- [ ] **Step 5: Commit**

```bash
git add council/router.py tests/test_router.py
git commit -m "feat(2c): router ranks by the requested capability's score"
```

---

### Task 5: `compose_council` — vendor-diverse top-K + adaptive size

**Files:**
- Create: `council/compose.py`
- Create: `tests/test_compose.py`

**Interfaces:**
- Produces:
  - `adaptive_k(capability: str) -> int` — `fast`→3, `code`→4, `general`→4, `reasoning`→5, else 4.
  - `compose_council(members: list[Member], *, k: int, capability: str) -> list[Member]` — score each by `m.scores.get(capability, max(m.scores.values()) if m.scores else 0)`; sort by (score, rpm) desc; pass 1 picks the top member of each distinct `provider_family`; pass 2 fills remaining slots by score; returns ≤ k members.

- [ ] **Step 1: Write `tests/test_compose.py`**

```python
from council.compose import adaptive_k, compose_council
from council.types import Member


def _m(alias, fam, score, cap="general", rpm=10):
    return Member(alias, "A", {cap: score}, rpm, fam)


def test_adaptive_k_by_capability():
    assert adaptive_k("fast") == 3
    assert adaptive_k("code") == 4
    assert adaptive_k("general") == 4
    assert adaptive_k("reasoning") == 5
    assert adaptive_k("unknown") == 4


def test_compose_prefers_distinct_families_first():
    members = [
        _m("a1", "alpha", 5), _m("a2", "alpha", 4),
        _m("b1", "beta", 3), _m("c1", "gamma", 2),
    ]
    picked = [m.alias for m in compose_council(members, k=3, capability="general")]
    # one per family before a second from alpha
    assert picked == ["a1", "b1", "c1"]


def test_compose_fills_remaining_by_score_after_families_exhausted():
    members = [_m("a1", "alpha", 5), _m("a2", "alpha", 4), _m("b1", "beta", 3)]
    picked = [m.alias for m in compose_council(members, k=3, capability="general")]
    assert picked[:2] == ["a1", "b1"]  # diversity first
    assert picked[2] == "a2"           # then next best regardless of family


def test_compose_ranks_by_requested_capability():
    coder = Member("coder", "A", {"code": 5, "general": 2}, 10, "x")
    gen = Member("gen", "A", {"code": 2, "general": 5}, 10, "y")
    assert compose_council([gen, coder], k=1, capability="code")[0].alias == "coder"


def test_compose_clamps_to_available():
    members = [_m("a1", "alpha", 5), _m("b1", "beta", 4)]
    assert len(compose_council(members, k=5, capability="general")) == 2


def test_compose_empty_returns_empty():
    assert compose_council([], k=3, capability="general") == []
```

- [ ] **Step 2: Run — expect failure**

Run: `.venv/bin/pytest tests/test_compose.py -q`
Expected: FAIL (module `council.compose` missing).

- [ ] **Step 3: Implement `council/compose.py`**

```python
from __future__ import annotations

from council.types import Member

_K_BY_CAPABILITY = {"fast": 3, "code": 4, "general": 4, "reasoning": 5}


def adaptive_k(capability: str) -> int:
    return _K_BY_CAPABILITY.get(capability, 4)


def _score(member: Member, capability: str) -> int:
    if not member.scores:
        return 0
    return member.scores.get(capability, max(member.scores.values()))


def compose_council(members: list[Member], *, k: int, capability: str) -> list[Member]:
    if not members or k <= 0:
        return []
    ranked = sorted(members, key=lambda m: (_score(m, capability), m.rpm), reverse=True)
    picked: list[Member] = []
    families: set[str] = set()
    for m in ranked:  # pass 1 — one per distinct provider family, strongest first
        if len(picked) >= k:
            break
        if m.provider_family not in families:
            picked.append(m)
            families.add(m.provider_family)
    for m in ranked:  # pass 2 — fill remaining slots by score
        if len(picked) >= k:
            break
        if m not in picked:
            picked.append(m)
    return picked[:k]
```

- [ ] **Step 4: Run — expect pass**

Run: `.venv/bin/ruff check . && .venv/bin/pytest tests/test_compose.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add council/compose.py tests/test_compose.py
git commit -m "feat(2c): vendor-diverse compose_council + adaptive council size"
```

---

### Task 6: Orchestrator `council` — manual/auto roster, adaptive size, notes

**Files:**
- Modify: `council/orchestrator.py`
- Modify: `tests/test_orchestrator.py`

**Interfaces:**
- Consumes: `compose.compose_council`, `compose.adaptive_k`, `router.classify`, `privacy.allowed_members`, `usage.available`.
- Produces: `Orchestrator.council(prompt, *, members: list[str]|None = None, size: int|None = None, sensitivity: str = "sensitive") -> CouncilResult` with `CouncilResult.note` describing roster decisions. Manual members filtered through the gate+usage (Tier-B dropped on sensitive, recorded in note; unknown dropped; empty→auto). `DEFAULT_MEMBER_ALIASES` removed.

- [ ] **Step 1: Write failing tests in `tests/test_orchestrator.py`**

```python
def test_council_auto_composes_vendor_diverse():
    rec = Recorder()
    r = asyncio.run(_orch(rec).council("explain the tradeoffs in depth please"))
    # sensitive -> only Tier-A (GLM/GROQ/CF); TIERB excluded
    assert {a.alias for a in r.per_member} == {
        "council/cerebras-glm-4.7", "council/groq-gpt-oss-120b", "council/cloudflare-llama-70b",
    }
    assert r.mode == "judge" and r.judge_used == "council/cerebras-glm-4.7"


def test_council_manual_roster_used():
    rec = Recorder()
    r = asyncio.run(_orch(rec).council("x", members=["council/groq-gpt-oss-120b"]))
    assert [a.alias for a in r.per_member] == ["council/groq-gpt-oss-120b"]


def test_council_manual_tier_b_dropped_on_sensitive():
    rec = Recorder()
    r = asyncio.run(_orch(rec).council(
        "x", members=["council/groq-gpt-oss-120b", "council/some-b"], sensitivity="sensitive"))
    aliases = {a.alias for a in r.per_member}
    assert "council/some-b" not in aliases
    assert "council/groq-gpt-oss-120b" in aliases
    assert "some-b" in r.note and "drop" in r.note.lower()
    assert all("council/some-b" != alias for alias, _ in rec.calls)  # never called


def test_council_manual_tier_b_allowed_on_public():
    rec = Recorder()
    r = asyncio.run(_orch(rec).council("x", members=["council/some-b"], sensitivity="public"))
    assert [a.alias for a in r.per_member] == ["council/some-b"]


def test_council_size_override():
    rec = Recorder()
    r = asyncio.run(_orch(rec).council("deep reasoning task", size=2))
    assert len(r.per_member) == 2


def test_council_unknown_alias_dropped_falls_back_to_auto():
    rec = Recorder()
    r = asyncio.run(_orch(rec).council("x", members=["council/nope"]))
    assert len(r.per_member) >= 1  # empty roster -> auto-composed
    assert "nope" in r.note
```

Update the old `test_council_default_trio_and_judge` → delete it (replaced by `test_council_auto_composes_vendor_diverse`). Keep `test_council_skips_exhausted_member` and `test_council_falls_back_when_all_exhausted` (compose runs over the post-usage pool, so both still hold).

- [ ] **Step 2: Run — expect failure**

Run: `.venv/bin/pytest tests/test_orchestrator.py::test_council_manual_tier_b_dropped_on_sensitive -q`
Expected: FAIL (`council` has no `members` list / note behaviour yet).

- [ ] **Step 3: Rewrite `council` in `council/orchestrator.py`**

Add imports at top: `from council import compose`. Remove `DEFAULT_MEMBER_ALIASES` and its constructor param/attribute. Replace the `council` method:

```python
    async def council(
        self, prompt: str, *, members: list[str] | None = None,
        size: int | None = None, sensitivity: str = "sensitive",
    ) -> CouncilResult:
        privacy.scan_secrets(prompt)
        allowed = privacy.allowed_members(self._members, sensitivity)
        if not allowed:
            raise NoEligibleMember("no members available for the requested sensitivity")
        pool = usage.available(allowed, self._counts()) or allowed
        notes: list[str] = []

        if members is not None:
            allowed_by_alias = {m.alias for m in allowed}
            pool_by_alias = {m.alias: m for m in pool}
            roster: list[Member] = []
            for alias in members:
                if alias in pool_by_alias:
                    roster.append(pool_by_alias[alias])
                elif self._by_alias(alias) is None:
                    notes.append(f"dropped {alias} (unknown)")
                elif alias not in allowed_by_alias:
                    tier = self._by_alias(alias).privacy_tier
                    notes.append(f"dropped {alias} (tier {tier} blocked on {sensitivity})")
                else:
                    notes.append(f"dropped {alias} (exhausted)")
            if roster:
                chosen = roster
            else:
                notes.append("manual roster empty after gate; auto-composed")
                chosen = await self._auto_roster(prompt, allowed, pool, size, notes)
        else:
            chosen = await self._auto_roster(prompt, allowed, pool, size, notes)

        answers = await fanout.fan_out(prompt, chosen, self._caller)
        merged, mode, disagreements, judge_used = await agg.aggregate(
            prompt, answers, caller=self._caller, judge_aliases=self._judge_order(chosen)
        )
        return CouncilResult(
            answer=merged, per_member=answers, disagreements=disagreements,
            judge_used=judge_used, mode=mode, note="; ".join(notes),
        )

    async def _auto_roster(
        self, prompt: str, allowed: list[Member], pool: list[Member],
        size: int | None, notes: list[str],
    ) -> list[Member]:
        capability = await router.classify(
            prompt, caller=self._caller, classifier_alias=self._classifier_for(allowed)
        )
        k = size if size is not None else compose.adaptive_k(capability)
        chosen = compose.compose_council(pool, k=k, capability=capability)
        notes.append(f"auto: {capability}, k={len(chosen)}")
        return chosen
```

Also remove `default_member_aliases` from `__init__` signature and body, and delete the `DEFAULT_MEMBER_ALIASES` constant.

- [ ] **Step 4: Run the orchestrator suite green**

Run: `.venv/bin/ruff check . && .venv/bin/pytest tests/test_orchestrator.py -q`
Expected: PASS. (`test_council_size_override` on "deep reasoning task": classify→reasoning, but size=2 → compose picks GLM+one other distinct-family Tier-A = 2.)

- [ ] **Step 5: Full suite**

Run: `.venv/bin/pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add council/orchestrator.py tests/test_orchestrator.py
git commit -m "feat(2c): dynamic council roster (manual/auto, adaptive size, gate-safe notes)"
```

---

### Task 7: MCP tool surface + usage rule (ergonomics)

**Files:**
- Modify: `consilium_mcp/server.py`
- Modify: `tests/test_mcp_server.py`
- Modify: `docs/usage-rule.md`

**Interfaces:**
- Consumes: `Orchestrator.council(members, size, sensitivity)` (Task 6).
- Produces: MCP `council(prompt, sensitivity="sensitive", members=None, size=None)` with self-documenting docstring; `_shape_council` includes `note`; `ask` docstring enumerates capabilities.

- [ ] **Step 1: Add failing tests to `tests/test_mcp_server.py`**

```python
def test_shape_council_includes_note():
    r = CouncilResult(
        answer="m", per_member=[MemberAnswer("council/x", True, "hi", "ok")],
        disagreements="none", judge_used="council/x", mode="judge", note="auto: code, k=4",
    )
    assert server._shape_council(r)["note"] == "auto: code, k=4"


def test_council_tool_passes_members_and_size(monkeypatch):
    captured = {}

    class FakeOrch:
        async def council(self, prompt, *, members=None, size=None, sensitivity="sensitive"):
            captured.update(prompt=prompt, members=members, size=size, sensitivity=sensitivity)
            return CouncilResult("a", [], "none", None, "judge", note="ok")

    monkeypatch.setattr(server, "_orch", FakeOrch())
    import asyncio
    asyncio.run(server.council("q", sensitivity="public", members=["council/x"], size=3))
    assert captured == {
        "prompt": "q", "members": ["council/x"], "size": 3, "sensitivity": "public",
    }
```

- [ ] **Step 2: Run — expect failure**

Run: `.venv/bin/pytest tests/test_mcp_server.py::test_council_tool_passes_members_and_size -q`
Expected: FAIL (`council` tool takes no `members`/`size`).

- [ ] **Step 3: Update `consilium_mcp/server.py`**

`_shape_council` — add `"note": r.note` to the returned dict. Replace the `council` tool and enrich `ask`:

```python
@mcp.tool()
async def ask(
    prompt: str, model: str | None = None, capability: str | None = None,
    sensitivity: str = "sensitive",
) -> dict:
    """Ask ONE best-fit free model for a quick second opinion or cheap bulk step.

    prompt: the question. Strip secrets/credentials first (the gate refuses obvious ones).
    model: pin a specific member alias (e.g. "council/github-gpt-4.1"); omit to auto-route.
    capability: force a strength axis — "reasoning" | "code" | "fast" | "general".
        Omit to auto-classify. Ignored when `model` is set.
    sensitivity: "sensitive" (default, Tier-A no-train providers only) or "public"
        (adds Tier-B providers that may train on the prompt). Use "public" ONLY for
        generic/published questions.
    Returns: {answer, model_used, capability, note}. `note` records routing/fallbacks.
    """
    return _shape_ask(
        await _get_orch().ask(prompt, model=model, capability=capability, sensitivity=sensitivity)
    )


@mcp.tool()
async def council(
    prompt: str, sensitivity: str = "sensitive",
    members: list[str] | None = None, size: int | None = None,
) -> dict:
    """Convene the council: fan out to several diverse free models and aggregate.

    Use for high-stakes cross-checks where diverse errors matter (costs more free-tier
    quota than `ask`).

    prompt: the question. Strip secrets/credentials first.
    sensitivity: "sensitive" (default, Tier-A only) or "public" (adds Tier-B). A Tier-B
        member is NEVER contacted on a sensitive prompt, even if named in `members`.
    members: pin an exact roster (list of member aliases). Omit to auto-compose the
        strongest vendor-diverse set for the classified task. Members blocked by the
        privacy gate or exhausted are dropped (see `note`).
    size: council size override (else adaptive 3-5 by task type). Ignored when `members`
        is given (its length wins).
    Returns: {answer, mode, judge_used, disagreements, per_member, note}. `note` records
        roster decisions (auto capability/size, dropped members, fallbacks).
    """
    return _shape_council(
        await _get_orch().council(
            prompt, sensitivity=sensitivity, members=members, size=size
        )
    )
```

- [ ] **Step 4: Run — expect pass**

Run: `.venv/bin/ruff check . && .venv/bin/pytest tests/test_mcp_server.py -q`
Expected: PASS.

- [ ] **Step 5: Update `docs/usage-rule.md`**

In the fenced rule block, replace the `council(...)` bullet with:
```markdown
- `council(prompt, sensitivity?, members?, size?)` — fan out to a diverse, auto-composed
  set of models and aggregate. `members` pins an exact roster (list of aliases); `size`
  overrides the adaptive 3-5 council size. Tier-B members are dropped on `sensitive`
  even if named. Use for high-stakes cross-checks (costs more free-tier RPD).
```

- [ ] **Step 6: Commit**

```bash
git add consilium_mcp/server.py tests/test_mcp_server.py docs/usage-rule.md
git commit -m "feat(2c): self-documenting council tool (members/size) + note in output"
```

---

### Task 8: LiteLLM-native rate-limit config + within-tier fallback safety test

**Files:**
- Modify: `proxy/config.yaml`
- Create: `tests/test_config_fallbacks.py`

**Interfaces:**
- Produces: `router_settings` with `allowed_fails`, `cooldown_time`, `retry_policy`, and a `fallbacks` list. A safety test asserts no Tier-A model lists a Tier-B fallback.

- [ ] **Step 1: Write `tests/test_config_fallbacks.py`**

```python
from pathlib import Path

import yaml

from council import registry

CONFIG = Path(__file__).resolve().parents[1] / "proxy" / "config.yaml"


def test_router_settings_have_retry_and_cooldown():
    data = yaml.safe_load(CONFIG.read_text())
    rs = data["router_settings"]
    assert rs["allowed_fails"] >= 1
    assert rs["cooldown_time"] >= 1
    assert "retry_policy" in rs


def test_fallbacks_never_cross_tiers():
    data = yaml.safe_load(CONFIG.read_text())
    tier = {m.alias: m.privacy_tier for m in registry.load_members(CONFIG)}
    for mapping in data["router_settings"].get("fallbacks", []):
        for primary, targets in mapping.items():
            for target in targets:
                assert tier[primary] == tier[target], (
                    f"{primary} ({tier[primary]}) must not fall back to "
                    f"{target} ({tier[target]})"
                )
```

- [ ] **Step 2: Run — expect failure**

Run: `.venv/bin/pytest tests/test_config_fallbacks.py -q`
Expected: FAIL (`router_settings` lacks `allowed_fails`/`cooldown_time`/`fallbacks`).

- [ ] **Step 3: Replace `router_settings` in `proxy/config.yaml`**

```yaml
router_settings:
  num_retries: 1
  allowed_fails: 2
  cooldown_time: 30
  retry_policy:
    TimeoutErrorRetries: 2
    InternalServerErrorRetries: 2
    RateLimitErrorRetries: 0
    AuthenticationErrorRetries: 0
    ContentPolicyViolationErrorRetries: 0
  # Same-tier, same-capability failover only. NEVER route Tier-A -> Tier-B.
  fallbacks:
    - council/cerebras-glm-4.7: [council/github-gpt-4.1, council/groq-gpt-oss-120b]
    - council/github-gpt-4.1: [council/cerebras-glm-4.7, council/groq-gpt-oss-120b]
    - council/groq-llama-70b: [council/cloudflare-llama-70b, council/groq-gpt-oss-120b]
```

- [ ] **Step 4: Run — expect pass**

Run: `.venv/bin/ruff check . && .venv/bin/pytest tests/test_config_fallbacks.py -q`
Expected: PASS (all fallback primaries/targets are Tier-A).

- [ ] **Step 5: Add a non-fatal optional-provider notice to `scripts/run-proxy.sh`**

After the required-vars check block (before the `CONSILIUM_CHECK_ONLY` block), insert:
```bash
optional=(GITHUB_API_KEY MISTRAL_API_KEY SAMBANOVA_API_KEY NVIDIA_NIM_API_KEY)
active=(); dormant=()
for var in "${optional[@]}"; do
  if [[ -n "${!var:-}" ]]; then active+=("$var"); else dormant+=("$var"); fi
done
echo "Optional providers active: ${active[*]:-none}; dormant: ${dormant[*]:-none}" >&2
```

- [ ] **Step 6: Verify the launcher still validates (check-only)**

Run: `CONSILIUM_CHECK_ONLY=1 bash scripts/run-proxy.sh`
Expected: prints the "Optional providers active: … dormant: …" line then "OK: all required env vars present …", exit 0.

- [ ] **Step 7: Commit**

```bash
git add proxy/config.yaml tests/test_config_fallbacks.py scripts/run-proxy.sh
git commit -m "feat(2c): LiteLLM native retry/cooldown/within-tier fallbacks + provider notice"
```

---

### Task 9: Live smoke — validate new providers & tier isolation, correct IDs

**Files:**
- Modify: `scripts/council-smoke.py`

**Interfaces:**
- Consumes: the running proxy + `~/.config/consilium/.env`. Not part of the CI gate (live network).

- [ ] **Step 1: Extend `scripts/council-smoke.py` to ping active new aliases and prove tier isolation**

Replace `_main` with:
```python
async def _main() -> int:
    key = os.environ.get("LITELLM_MASTER_KEY", "")
    if not key:
        print("ERROR: LITELLM_MASTER_KEY not set", file=sys.stderr)
        return 2
    o = orch.build(api_key=key)

    # 1) ping each active member with a 1-token question
    from council import registry
    present = registry.available_env_keys()
    members = registry.load_members("proxy/config.yaml", available_keys=present)
    print(f"[active members] {len(members)}: {[m.alias for m in members]}")
    for m in members:
        try:
            r = await o.ask("Reply with the single word: ok", model=m.alias,
                            sensitivity="public")
            print(f"  ok  {m.alias}: {r.answer.strip()[:40]}")
        except Exception as exc:  # noqa: BLE001 - smoke: report and continue
            print(f"  ERR {m.alias}: {exc.__class__.__name__}: {exc}")

    # 2) public council may include Tier-B
    pub = await o.council("Name one risk of free-tier LLM routing.", sensitivity="public")
    print(f"[public council] note={pub.note}")
    for a in pub.per_member:
        print(f"  {'ok ' if a.ok else 'ABS'} {a.alias}")

    # 3) sensitive council must contact NO Tier-B member
    tier = {m.alias: m.privacy_tier for m in members}
    sen = await o.council("Explain one tradeoff of self-hosting an LLM proxy.",
                          sensitivity="sensitive")
    contacted_b = [a.alias for a in sen.per_member if tier.get(a.alias) == "B"]
    print(f"[sensitive council] note={sen.note} tier-B contacted={contacted_b}")
    assert not contacted_b, f"PRIVACY LEAK: Tier-B contacted on sensitive: {contacted_b}"
    print("[tier isolation] OK — no Tier-B on sensitive")
    return 0
```

- [ ] **Step 2: Start the proxy and run the smoke**

```bash
set -a; source ~/.config/consilium/.env; set +a
nohup bash scripts/run-proxy.sh >/tmp/consilium-proxy.log 2>&1 &
sleep 8
.venv/bin/python scripts/council-smoke.py
```
Expected: each GitHub/Mistral/SambaNova alias prints `ok` (NVIDIA absent from active list); public council may list Tier-B; sensitive council prints "tier isolation OK".

- [ ] **Step 3: Correct any 404/unknown-model IDs in `proxy/config.yaml`**

For any alias that printed `ERR ... NotFound/404`, query the provider's live catalog and fix the `model:` id, then re-run Step 2 until all active aliases return `ok`. Example catalog checks:
```bash
curl -s https://models.github.ai/catalog/models -H "Authorization: Bearer $GITHUB_API_KEY" | head
curl -s https://api.mistral.ai/v1/models -H "Authorization: Bearer $MISTRAL_API_KEY" | head
curl -s https://api.sambanova.ai/v1/models -H "Authorization: Bearer $SAMBANOVA_API_KEY" | head
```
If an `rpd`/`tpd` free-tier limit is discovered, encode it in the alias's `model_info`.

- [ ] **Step 4: Re-run the gate (config edits must keep unit tests green)**

Run: `.venv/bin/ruff check . && .venv/bin/pytest -q`
Expected: PASS (registry still loads 13; fallback tiers still consistent).

- [ ] **Step 5: Commit**

```bash
git add scripts/council-smoke.py proxy/config.yaml
git commit -m "test(2c): live smoke for new providers + tier-isolation assertion"
```

---

## Self-review

**Spec coverage:**
- Provider catalog (2/provider) → T2. Dossier `scores`+`provider_family`+legacy synth → T1. `ask` capability-score → T4. Manual/auto/adaptive-K/vendor-diversity council → T5+T6. Hard gate incl. manual Tier-B drop → T6 (`test_council_manual_tier_b_dropped_on_sensitive`) + T9 live assertion. Key-presence activation → T3. MCP ergonomics + usage-rule → T7. LiteLLM native rate-limit + within-tier fallbacks → T8. Env/secrets validation → T8 (run-proxy notice). Testing (unit + live) → each task + T9. Errors (unknown alias, inactive, exhausted) → T6/T3. Out-of-scope (aggregation) untouched. All covered.

**Placeholder scan:** No TBD/TODO. Model IDs flagged provisional with an explicit live-validation-and-correct step (T9), matching the Cerebras-drift precedent — not a silent placeholder.

**Type consistency:** `Member(alias, privacy_tier, scores, rpm, provider_family="", rpd=None, tpd=None)` used identically in every task and every migrated test. `capabilities`/`strength` are read-only properties (used by `usage.summary`, `_judge_order`, unchanged). `compose_council(members, *, k, capability)` and `adaptive_k(capability)` signatures match between T5 definition and T6 use. `council(prompt, *, members: list[str]|None, size: int|None, sensitivity)` matches between orchestrator (T6), MCP tool (T7), and tests. `CouncilResult.note` added in T1, produced in T6, surfaced in T7. `registry.load_members(config_path, *, available_keys=None)` and `available_env_keys(...)` consistent T3↔build↔T9.
