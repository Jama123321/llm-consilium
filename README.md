# LLM Consilium

A global, VM-wide **council of free cloud LLMs** any Claude Code project on this
machine can consult for a second opinion, a diverse cross-check, or bounded
parallel work — with **privacy-safe routing** (private code never reaches a
provider that trains on it). Interim multi-model compute until a local model exists.

- **What / why / how:** see [`CLAUDE.md`](./CLAUDE.md).
- **Full bootstrap brief for a fresh session:** see [`SUPERPROMPT.md`](./SUPERPROMPT.md).
- **Design basis (2026 free-LLM audit):** [`docs/research/free-llm-consilium-audit-2026.md`](./docs/research/free-llm-consilium-audit-2026.md).

**Architecture:** LiteLLM proxy (`localhost:4000/v1`) → council orchestrator
(privacy gate → fan-out → aggregate) → user-scope MCP `council` tool available in
every project.

**Status:** Phase 0 (MVP proxy) — not started. Start with the brainstorming skill.
