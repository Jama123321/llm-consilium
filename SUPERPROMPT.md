# SUPERPROMPT — bootstrap brief for the LLM Consilium project

> Paste-and-go context for a fresh Claude Code session started in this repo.
> Read `CLAUDE.md` first (project rules), then this (the vision + decisions + first
> steps), then `docs/research/free-llm-consilium-audit-2026.md` (the design basis).

## What we are building

A **global, VM-wide council of free cloud LLMs** that any Claude Code project on
this machine can call for a second opinion, a diverse cross-check, or bounded
parallel work. Claude (paid) stays the primary reasoner; the council is a
**tool/subagent** it invokes. The council fans one prompt out to K free models from
different vendors and aggregates their answers. It is the interim multi-model layer
until a local model exists.

## Decisions already made (do not re-litigate — build on these)

1. **3-layer architecture:** (1) a single **LiteLLM proxy** on `127.0.0.1:4000`
   exposing one OpenAI-compatible `/v1` for every provider; (2) a thin **council
   orchestrator** (privacy gate → fan-out with per-member RPM semaphores + timeout
   + quorum → aggregate by vote or judge-synthesis); (3) a **user-scope MCP server**
   exposing a `council` tool so it is available in every project, plus a user-level
   rule in `~/.claude/CLAUDE.md`.
2. **Router = self-hosted LiteLLM** (NOT OpenRouter-hosted — that caps you at pooled
   `:free` limits and hides upstream privacy; NOT direct per-provider SDK calls —
   too many auth schemes). LiteLLM keeps each provider's *native* free limits and
   reduces every provider to `{alias, model_id, base_url, api_key_env, rpm, tpm,
   privacy_tier}`.
3. **Privacy tiering is the backbone.** Tier A (Cerebras, Cloudflare, Groq-ZDR) =
   safe for any prompt (no training/retention). Tier B (Gemini free, Mistral free,
   Cohere trial, GLM/DeepSeek, unconfirmed) = public prompts only. The privacy gate
   runs on **every** fan-out; secrets/`.env` go to **no** free tier.
4. **Council chair/judge = Cerebras qwen-3-235b** (1M tokens/day, Tier A, strong).
   Voters: pick 4–6 heterogeneous-by-vendor members from the audit's top list.
5. **Stack = Python** (LiteLLM + MCP are Python-native), `pytest` + `ruff` gate.
6. **Free-first, no card:** Cerebras, Groq, Cloudflare, Google AI Studio, NVIDIA
   NIM. Keys in `~/.config/consilium/.env` (chmod 600, never committed).
7. **Dev here, deploy globally** — source in this repo; runtime (service, env, MCP
   registration, user rule) is global on the VM.

## The phased plan (start at Phase 0)

- **Phase 0 — MVP compute:** LiteLLM proxy up on `localhost:4000` with **3 Tier-A
  providers** (Cerebras + Groq + Cloudflare); `curl localhost:4000/v1/models` and a
  single completion work. Deliverable: reproducible `proxy/` config + a run script.
- **Phase 1 — MVP council:** `council/` orchestrator — privacy gate + parallel
  fan-out to the members + a judge-synthesis aggregate; a CLI `council "question"
  [--sensitive]`. Proven on a couple of questions.
- **Phase 2 — global Claude integration:** user-scope MCP server exposing the
  `council` tool (`claude mcp add --scope user`), plus the usage rule appended to
  `~/.claude/CLAUDE.md` (when to consult, privacy tiering, rate-limit hygiene).
- **Phase 3 — hardening:** systemd `--user` service (always-on across reboots),
  add remaining providers, rate-limit/quota telemetry, failover tuning.

## First move for this session

Do **NOT** jump to code. Start with the **brainstorming** skill to design **Phase 0**
concretely: exact provider set + model ids for the MVP, the `proxy/` LiteLLM config
shape, how keys are provisioned (which consoles, no-card path), the run/health
check, and how the privacy tier is attached per model. Present the design, get user
approval, write the spec to `docs/superpowers/specs/`, then `writing-plans`, then
`subagent-driven-development` (all subagents on Opus). Business context before the
wave.

## Guardrails

- Secrets never in code/logs/memory/git — only `~/.config/consilium/.env` (chmod 600).
- Every fan-out passes the privacy gate; unconfirmed provider policy → Tier B.
- Don't merge to `main` without explicit user OK. No `Co-Authored-By` in commits.
- The 2026 audit's exact RPM/RPD numbers shift monthly — verify in each provider's
  console before hard-coding limits.

## Open questions to resolve with the user during brainstorming

- Exactly which 4–6 voters for the default quorum (cost/diversity trade-off).
- Aggregate strategy default: majority-vote vs always judge-synthesis vs adaptive.
- CLI-first or MCP-first for Phase 1 (recommend CLI first, MCP in Phase 2).
- Where the global runtime env lives (`~/.config/consilium/` proposed).
