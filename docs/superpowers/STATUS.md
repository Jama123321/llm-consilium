# LLM Consilium — project STATUS / handoff (as of 2026-07-14)

Durable state map so work survives a context compaction. Trust `git log`, the SDD
ledger (`.superpowers/sdd/progress.md`, git-ignored), and this doc over recollection.

## Phase map
- **Phase 0 — Compute:** LiteLLM proxy on 127.0.0.1:4000 + 3 Tier-A providers (Cerebras/Groq/Cloudflare). ✅ MERGED to `main` (PR #1 lineage), live-validated.
- **Phase 1 — Council + MCP:** engine (`registry·privacy·client·router·fanout·aggregate·orchestrator`) with `ask`/`council`, adaptive aggregate, rate-limit fallback, total privacy gate; MCP server `consilium_mcp` (ask/council); usage protocol. ✅ MERGED to `main` (PR #1) + closeout (PR #2).
- **Phase 2 — Deployment hardening:**
  - **2a — Integration + always-on:** systemd `--user` proxy service + linger; `server.py` standalone import fix; `claude mcp add --scope user`; `~/.claude/CLAUDE.md` rule. ✅ MERGED (PR #3). Live: service active+enabled+linger, MCP `✔ Connected`.
  - **2b — Rate-limit robustness:** SQLite usage store (requests+tokens/day), `rpd`/`tpd` caps, client token-recorder + backoff (timeout/5xx, not 429), orchestrator rotation past caps, `scripts/usage.py` CLI + `stats` MCP tool. ✅ MERGED (PR #4), live-validated (usage recorded end-to-end).

## Branch / merge state
- `main` @ ~5db53a7 — **Phases 0, 1 (+closeout), 2a, 2b ALL merged** (PRs #1–#4). 94 tests green, ruff clean. No open feature branches.
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
1. ✅ Merge 2a + 2b to `main` (PRs #3/#4) — DONE.
2. (context compact here — this doc + memories + research are the durable record.)
3. **Phase 2c — providers + robustness.**
4. **(2d) council-quality sprint** (aggregation borrows) — optional, high-ROI.
5. **Phase 3 — distribution.**

## Borrow roadmap (what we take from the research, and WHEN)
Business framing: **2c makes the council stronger & cheaper to run; 2d makes its answers better/less-biased; Phase 3 makes it shareable.** License rule: MIT/Apache = copy with attribution (NOTICE); AGPL / no-license = **reimplement design only** (keep our repo MIT-shareable for Phase 3).

**Phase 2c (next):**
- **Add GitHub Models (Tier A)** first — GPT-class, no card, documented no-train → strengthens the *safe* tier. Then Mistral/SambaNova/NVIDIA-NIM as **Tier B** (public-only breadth). *Correction from research: NIM & SambaNova are B, not A.*
- **Use LiteLLM's native rate-limit config** (`rpm/tpm/allowed_fails/cooldown_time/retry_policy/fallbacks`) — we hand-rolled some rotation; the built-ins cut maintenance + give robust failover. Business: less code, more reliability.
- **Provider-diversity fan-out** (FreeLLMAPI `diversifyChain`, MIT) — council fans out to genuinely different provider families → more diverse errors → better cross-check.

**2d — council-quality sprint (after 2c, optional but high-ROI):**
- **Anonymized synthesis + code-names** (ai-council, MIT) — hide which model said what before the judge merges → kills brand bias → better merged answers. Cheapest, highest ROI.
- **Better judge prompt** (FreeLLMAPI Fusion, MIT) — "rewrite standalone, reason don't average" → higher-quality council output.
- **Peer-rank mode** (karpathy, reimplement) + **stance/debate mode** (PAL, Apache) — extra aggregation modes for hard/contentious questions.
- **Convergence early-exit + confidence** (DUH, reimplement) — save quota on debates + trust scores. Advanced/last.

**Phase 3 — distribution:**
- **`consilium init` wizard** (key-presence activation from PAL; idempotent re-runnable from FreeLLMAPI): prompts for the Tier-A keys the colleague has → live 1-token ping → green/red readiness table.
- **One-line path-agnostic installer** (removes the hardcoded `/opt/...` paths): venv+deps+`.env` chmod600 + `claude mcp add` + start service.
- **README positioning:** lead with the privacy hook (our differentiation), Tier-A/B table; keep **MIT** license.

None is required — the council works today. Each phase is its own brainstorm→spec→plan→SDD.
