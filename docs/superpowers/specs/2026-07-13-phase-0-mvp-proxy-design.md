# Phase 0 MVP — LiteLLM Proxy (Tier-A compute layer)

**Date:** 2026-07-13
**Status:** Design approved — pending written-spec review, then `writing-plans`.
**Design basis:** `docs/research/free-llm-consilium-audit-2026.md`, `CLAUDE.md`, `SUPERPROMPT.md`.

## 1. Goal & scope

Stand up the **compute layer** (Architecture Layer 1): a single OpenAI-compatible
`/v1` on `127.0.0.1:4000`, self-hosted **LiteLLM proxy**, fronting **3 Tier-A
providers** — **Cerebras, Groq, Cloudflare Workers AI**. "Done" = the proxy comes up
reproducibly and a health-check proves each provider answers a real completion
end-to-end.

**In scope:** proxy config, run script, live health-check, dependency pinning,
CI-safe tests, secrets contract.
**Explicitly out of scope (later phases):** privacy gate, fan-out/aggregate, quorum,
semaphores, the MCP tool, systemd service, any Tier-B provider.

### Tier-A only — deliberate safety property, not just smaller scope

Phase 0 registers **only Tier-A** providers (no training / no retention on free tier).
The privacy gate that distinguishes Tier A from Tier B lives in **Phase 1**. Until
that gate exists and enforces routing, **no Tier-B endpoint may be reachable** —
otherwise nothing prevents a sensitive prompt from reaching a provider that trains on
it. The config schema carries a `privacy_tier` tag per alias, so adding Tier-B later
(Phase 3) is a config edit under a working gate — the design is forward-compatible,
but Tier-B endpoints do not appear in Phase 0.

## 2. Decisions locked in this session

- **Runtime:** Python **3.10** (installed 3.10.12; LiteLLM fully supports it) + a
  project-local `./.venv/` (already gitignored). Update CLAUDE.md wording
  `Python 3.11+` → `Python 3.10+`.
- **Models:** curated set (~5 aliases), enough to seed the Phase-1 council.
- **Health-check:** live — `GET /v1/models` **plus** a 1-token completion to **each**
  provider, per-provider pass/fail, non-zero exit on any failure.
- **No DB/UI:** stateless, config-only proxy (no Postgres, no admin UI) for the MVP.
- **Proxy binds `127.0.0.1` only**, with a `LITELLM_MASTER_KEY` for hygiene.

## 3. Components (each one responsibility)

| Unit | Responsibility | Depends on |
|---|---|---|
| `proxy/config.yaml` | Declarative provider registry: aliases, `model` id, `api_base`/`api_key` via `os.environ/*`, conservative `rpm`, `model_info.privacy_tier` tag | env vars |
| `.env.example` (committed) | Secrets contract: which vars, and which console gives each key (no-card path) | — |
| `~/.config/consilium/.env` (chmod 600, **never committed**) | The actual keys | provider consoles |
| `scripts/run-proxy.sh` | Load env, fail-fast on any missing required var, launch `litellm` on `127.0.0.1:4000` | config + env |
| `scripts/healthcheck.py` | `GET /v1/models` + a 1-token completion per provider; print per-provider pass/fail; non-zero exit on any failure | running proxy |
| `tests/` | Unit tests: config shape (aliases present, each has `privacy_tier`, no literal secrets) + healthcheck logic (httpx mocked). **Run in CI without keys.** | — |
| `requirements.txt` | Pinned deps: `litellm[proxy]`, `httpx`, `pytest`, `ruff` | — |

## 4. Providers & models (curated set — 5 aliases, all Tier-A)

| Alias | Provider / model | Notes |
|---|---|---|
| `council/cerebras-qwen-235b` | Cerebras `qwen-3-235b` | future chair/judge; 1M tok/day |
| `council/cerebras-llama-70b` | Cerebras `llama-3.3-70b` | |
| `council/groq-llama-70b` | Groq `llama-3.3-70b-versatile` | |
| `council/groq-gpt-oss-120b` | Groq `openai/gpt-oss-120b` | |
| `council/cloudflare-llama-70b` | Cloudflare `@cf/meta/llama-3.3-70b-instruct-fp8-fast` | 10k neurons/day |

**Exact model ids are pinned from each provider's live catalog during
implementation** — the audit warns ids/limits drift monthly; the health-check surfaces
any mismatch.

## 5. LiteLLM wiring

- **Cerebras / Groq** — native LiteLLM prefixes (`cerebras/…`, `groq/…`); key via
  `os.environ/CEREBRAS_API_KEY` / `os.environ/GROQ_API_KEY`.
- **Cloudflare** — `openai/`-shim against CF's OpenAI-compat endpoint. To avoid
  interpolating the account id mid-URL, the **full** base lives in env:
  `CLOUDFLARE_API_BASE=https://api.cloudflare.com/client/v4/accounts/<ACCOUNT_ID>/ai/v1`,
  plus `CLOUDFLARE_API_TOKEN`. (Native `cloudflare/` provider is the fallback path if
  the shim misbehaves.)
- **Privacy tier tag** — `model_info: { privacy_tier: A }` on every alias; Phase 1
  reads it via `/v1/model/info`. Convention established now.
- **Router settings** — minimal for Phase 0: `num_retries: 1`, conservative per-model
  `rpm` (Cerebras ~5, Groq ~30; Cloudflare governed by neurons, no rpm). No fallbacks
  yet (member-drop is the council's job in Phase 1).

Config sketch (illustrative — ids/rpm confirmed at implementation):

```yaml
model_list:
  - model_name: council/cerebras-qwen-235b
    litellm_params:
      model: cerebras/qwen-3-235b
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

## 6. Secrets contract

`~/.config/consilium/.env` (chmod 600) holds, and only referenced via `os.environ/*`
in config — **never literal in code/config/logs/git**:

| Var | Where to get it (no card) |
|---|---|
| `CEREBRAS_API_KEY` | cloud.cerebras.ai → API Keys |
| `GROQ_API_KEY` | console.groq.com → API Keys |
| `CLOUDFLARE_API_TOKEN` | dash.cloudflare.com → My Profile → API Tokens → "Workers AI" template |
| `CLOUDFLARE_API_BASE` | full URL with your Account ID (from the dashboard sidebar) |
| `LITELLM_MASTER_KEY` | self-generated `sk-...` (proxy auth hygiene) |

`.env.example` (committed) documents these with placeholder values only.

## 7. Data flow & error handling

**Health path:** `run-proxy.sh` → litellm(config + env) → `127.0.0.1:4000/v1`.
`healthcheck.py` → `GET /v1/models` (expects the 5 aliases) → `POST
/v1/chat/completions` to each provider alias with `max_tokens: 1` → aggregate pass/fail
→ exit code.

- Missing required env var → `run-proxy.sh` **fails fast** with a clear message before
  launching.
- Provider 401 / 429 / timeout in the health-check → recorded as **FAIL** for that
  provider with its status; does **not** abort the other probes; script exits non-zero
  if any provider failed (a real gate).
- Secrets are never printed — the health-check logs alias + status only.

## 8. Testing & the hard gate

`ruff` clean + `pytest` green is the completion gate, satisfied by tests that need **no
live keys**:

- **Config-shape tests:** `proxy/config.yaml` parses; the 5 expected aliases exist;
  every alias carries `model_info.privacy_tier`; no value is a literal secret (all
  credential fields reference `os.environ/`).
- **Health-check logic tests:** result aggregation and exit-code logic with `httpx`
  mocked (success, 401, 429, timeout cases).

The **live** health-check is a documented one-time smoke run the user performs after
placing keys in `~/.config/consilium/.env`. It is not part of the CI pytest gate.

## 9. Deliverables

1. `proxy/config.yaml` — 5 Tier-A aliases, env-referenced creds, `privacy_tier` tags.
2. `.env.example` — secrets contract with provisioning notes.
3. `scripts/run-proxy.sh` — env load + fail-fast + launch on `127.0.0.1:4000`.
4. `scripts/healthcheck.py` — live per-provider probe with pass/fail + exit code.
5. `requirements.txt` — pinned deps.
6. `tests/` — config-shape + healthcheck-logic unit tests (CI-safe).
7. CLAUDE.md edit: `Python 3.11+` → `Python 3.10+`.

## 10. Acceptance criteria

- `./scripts/run-proxy.sh` brings the proxy up on `127.0.0.1:4000`; `curl
  localhost:4000/v1/models` lists the 5 aliases.
- `python scripts/healthcheck.py` returns a real completion from **each** of Cerebras,
  Groq, Cloudflare and exits 0 (with valid keys present).
- `ruff` clean and `pytest` green with no keys present.
- No secret appears in any tracked file, log line, or the config.

## 11. Open note (non-blocking): Groq Tier-A / ZDR

Groq does **not** train on prompts (the decisive Tier-A criterion in CLAUDE.md) → tagged
`privacy_tier: A`. Its free tier keeps 7-day operational logs by default; full
zero-retention needs ZDR. Recorded as a config comment; enabling ZDR is a later action
and does not block Phase 0.
