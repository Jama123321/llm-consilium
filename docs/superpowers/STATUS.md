# LLM Consilium — project STATUS / handoff (as of 2026-07-14)

Durable state map so work survives a context compaction. Trust `git log`, the SDD
ledger (`.superpowers/sdd/progress.md`, git-ignored), and this doc over recollection.

## Phase map
- **Phase 0 — Compute:** LiteLLM proxy on 127.0.0.1:4000 + 3 Tier-A providers (Cerebras/Groq/Cloudflare). ✅ MERGED to `main` (PR #1 lineage), live-validated.
- **Phase 1 — Council + MCP:** engine (`registry·privacy·client·router·fanout·aggregate·orchestrator`) with `ask`/`council`, adaptive aggregate, rate-limit fallback, total privacy gate; MCP server `consilium_mcp` (ask/council); usage protocol. ✅ MERGED to `main` (PR #1) + closeout (PR #2).
- **Phase 2 — Deployment hardening:**
  - **2a — Integration + always-on:** systemd `--user` proxy service + linger; `server.py` standalone import fix; `claude mcp add --scope user`; `~/.claude/CLAUDE.md` rule. ✅ DONE, **UNMERGED** on branch `phase-2a-integration` (4 commits). Live: service active+enabled+linger, MCP `✔ Connected`.
  - **2b — Rate-limit robustness:** SQLite usage store (requests+tokens/day), `rpd`/`tpd` caps, client token-recorder + backoff (timeout/5xx, not 429), orchestrator rotation past caps, `scripts/usage.py` CLI + `stats` MCP tool. ✅ DONE, final review "ready to merge", live-validated (usage recorded end-to-end). **UNMERGED** on branch `phase-2b-ratelimit` (9 commits).

## Branch / merge state
- `main` @ 7e20a1f — Phase 0 + 1 (+ closeout) merged.
- `phase-2a-integration` — done, unmerged, independent files (deploy/, scripts/install*, consilium_mcp/server.py, tests).
- `phase-2b-ratelimit` — done, unmerged, from main; files disjoint from 2a (council/usage.py, client/orchestrator/registry/types, proxy/config.yaml caps, scripts/usage.py, stats tool).
- **Pending decision:** batch-merge 2a + 2b into `main` (via PRs, like Phase 1). Needs explicit user OK (CLAUDE.md rule). Recommended before next big work.
- GitHub: private repo `Jama123321/llm-consilium`.

## Deployed runtime (global on the VM)
- systemd `--user` service `consilium-proxy` (active, enabled, linger on) → proxy on 127.0.0.1:4000.
- MCP `consilium` registered `--scope user` → tools `ask`, `council`, `stats` (restart Claude Code to see them in an open session).
- `~/.claude/CLAUDE.md` holds the usage rule. Secrets only in `~/.config/consilium/.env` (chmod 600). Usage DB at `~/.config/consilium/usage.db`.

## Deferred backlog (Phase-2 hardening / follow-ups)
- 2b Minor (fail-safe): empty-200 response records nothing (under-counts); no corrupt-writable-DB test; unwritable-path test non-hermetic under uid 0.
- 1c/earlier Minors: secret-scan `sk-proj-` shapes; broad-except in fanout; a few test-coverage/hygiene nits.
- Bigger: exponential backoff for 429; RPD daily rotation across sessions is per-day only; cost/$ tracking; multi-day history.

## Research (2026-07-14, done)
- `docs/research/prior-art-comparison-2026-07-14.md` — free-council+MCP is a crowded category (FreeLLMAPI 16k★, PAL 11.7k★, karpathy 22k★, DUH, ai-council-mcp). **Our unoccupied differentiation = privacy-tiering by provider free-tier train-policy in a free-council MCP.**
- `docs/research/borrow-map-2026-07-14.md` — what to reuse (ai-council synthesis prompt+code-names MIT; FreeLLMAPI Fusion judge+diversity MIT; PAL stance-steering Apache; karpathy peer-rank & DUH convergence = design-only). **Free win:** use LiteLLM native rpm/tpm/allowed_fails/cooldown/retry/fallbacks. **Provider correction: NVIDIA NIM & SambaNova are Tier B (not A); GitHub Models is a Tier-A add — do it first in 2c.**

## Next steps (proposed order)
1. Merge 2a + 2b to `main` (batch PRs) — pending user OK.
2. (context compact here — this doc + memories + research are the durable record.)
3. **Phase 2c — providers:** add GitHub Models (Tier A first), then Mistral/SambaNova/NIM as Tier B (public-only); configure LiteLLM native rate-limit knobs; optionally borrow the diversity fan-out + anonymized synthesis.
4. **Phase 3 — distribution:** public-repo positioning (lead with privacy hook, MIT), `consilium init` key wizard + path-agnostic installer, README for colleagues.
