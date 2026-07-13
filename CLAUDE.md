# LLM Consilium — global free-LLM council for this VM

A VM-wide service that lets **any** Claude Code project on this machine consult a
**council of free cloud LLMs** (fan-out → aggregate) for second opinions,
cross-checking, and cheap parallel work — with **privacy-safe routing**. It is the
interim multi-model compute layer until a local model exists. This project is
**not** part of any single product (e.g. cognitive-kernel); it is developed here
and **deployed globally** on the VM.

## Vision

Claude (the paid driver in Claude Code) stays the primary reasoner. When it wants
a second opinion, a diverse cross-check, or to parallelise a bounded question, it
calls the **council**: the same prompt fans out to K free models from different
vendors (diverse errors), and the answers are aggregated (majority vote for facts,
or a judge-model synthesis). Every fan-out is gated by **data-sensitivity** so
private code never reaches a provider that trains on it.

## Architecture — 3 layers

| Layer | What | Where it runs |
|---|---|---|
| **1. Compute** | A single **LiteLLM proxy** exposing one OpenAI-compatible `/v1` on `127.0.0.1:4000`. One config, all providers, all keys. | Global service (`systemctl --user`, or `nohup`/tmux for the MVP). |
| **2. Council** | A thin orchestrator: takes `{prompt, sensitivity}`, applies the **privacy gate**, fans out to K members through the proxy (per-member RPM semaphores + timeout + quorum), aggregates (vote / judge-synthesis). | Global (called by layer 3). |
| **3. Claude integration** | A **user-scope MCP server** exposing a `council` tool → available in **every** project. Plus a **user-level rule** in `~/.claude/CLAUDE.md` on when/how to use it. | Global (`claude mcp add --scope user`). |

**Dev vs deploy:** source lives in **this repo**; the runtime artifacts (LiteLLM
service, `~/.config/consilium/.env`, the user-scope MCP registration, the
`~/.claude/CLAUDE.md` rule) are **global** on the VM. Keep them separate.

## Privacy tiering — the core safety rule

Free tiers are "free" because some pay with your data. Split providers by whether
the **free tier trains on / retains** your prompts:

- **Tier A — SAFE for ANY prompt** (ToS: no training, no retention / retention off):
  **Cerebras, Cloudflare Workers AI, Groq (with ZDR).** Private repo code is OK here.
- **Tier B — PUBLIC / non-sensitive prompts ONLY** (trains on or retains free-tier
  data): **Google Gemini (free), Mistral (free), Cohere trial, Chinese GLM/DeepSeek,
  and any provider whose free-tier policy is undocumented.**

**Hard rules:**
- The council's privacy gate runs on **every** fan-out: a **sensitive** prompt
  (contains repo code / internal data) routes to **Tier A only**; a **public**
  prompt may use A+B.
- **Secrets / `.env` / credentials → NEVER to ANY free tier** (not even Tier A).
- When a provider's policy is unconfirmed, default it to **Tier B**.

Design basis (providers, limits, OpenAI-compat, per-provider privacy verdicts,
LiteLLM config shape, council pattern): **`docs/research/free-llm-consilium-audit-2026.md`**.

## Stack (planned)

- **Python 3.11+** (LiteLLM + MCP are Python-native), `asyncio`/`httpx` for the
  fan-out, `pytest` for tests, `ruff` for lint/format.
- **LiteLLM** proxy (routing + per-key rate-limit + failover).
- **MCP Python SDK** for the user-scope `council` tool.
- Free-first providers (no card): **Cerebras, Groq, Cloudflare Workers AI, Google
  AI Studio, NVIDIA NIM**; keys in `~/.config/consilium/.env` (chmod 600).

## Planned structure (built during dev)

```
llm-consilium/
├── CLAUDE.md                    # this file
├── SUPERPROMPT.md               # full bootstrap brief for a fresh session
├── README.md
├── proxy/                       # LiteLLM config (models, aliases, rpm, privacy_tier)
├── council/                     # orchestrator: privacy gate, fan-out, aggregate
├── mcp/                         # user-scope MCP server exposing the `council` tool
├── scripts/                     # CLI wrapper (`council "question"`), install/service scripts
├── tests/
└── docs/
    ├── research/free-llm-consilium-audit-2026.md   # design basis (the 2026 audit)
    └── superpowers/{specs,plans}/                  # brainstorm specs + implementation plans
```

## Secrets

- One global env file `~/.config/consilium/.env` (chmod 600), loaded by the
  service. **Never** committed, **never** written to memory, **never** in code.
- `.gitignore` excludes `.env`, `*.key`, `__pycache__/`, local venvs.

## Conventions

- Small, testable units with clear boundaries; each file one responsibility.
- No secrets in code or logs. Log prompts only when the target is a Tier-A provider
  and only at debug.
- Errors explicit (typed), no silent failures; a dead provider degrades the council
  (drops that voter), never crashes it.
- Python: `ruff` clean + `pytest` green is the hard gate before any task is "done".
- Commits: English, imperative. **No `Co-Authored-By` trailer.** Never force-push /
  `--no-verify`. Branch first; **do not merge to `main` without explicit user OK.**

## Workflow (same discipline as cognitive-kernel)

Every task goes **brainstorm → spec → plan → execute → review → gate**. Use the
superpowers skills:
- **brainstorming** first for anything you build (design + user approval before code).
- **writing-plans** → a task-by-task plan.
- **subagent-driven-development** to execute (fresh subagent per task + 2-verdict
  review: spec-compliance + code-quality + a final whole-branch review). **All
  subagents on Opus.**
- **Hard gate before `completed`:** `ruff` + `pytest` green.

Workflow variants (pick by size):
- **Phase plan** — a new phase / major milestone: write `docs/superpowers/…` phase doc.
- **Wave FULL** — ≥3 tasks, external integrations (real provider APIs), or public
  interface changes: spec + 2-stage review + smoke.
- **Wave SLIM** — ≤2 tasks, pure refactor/docs/config, no external calls.

Business context before each wave (3-5 sentences: why it serves the council), then
the technical breakdown.

## Memory

File-based memory (same as the other projects): one fact per file with frontmatter
(`user | feedback | project | reference`), a one-line pointer in `MEMORY.md`.
Convert relative dates to absolute. Don't store what the repo already records.

## Git / remote

Local git for now (add a private GitHub remote when the MVP works). English
identity, no Claude attribution in commits.

## Status

**Phase 0 not started.** Design basis is the 2026 audit in `docs/research/`. First
move: brainstorm the **Phase 0 MVP** — LiteLLM proxy + 3 Tier-A providers
(Cerebras + Groq + Cloudflare) reachable at `localhost:4000/v1`, then a minimal
council fan-out, then the user-scope MCP tool + the global usage rule.
