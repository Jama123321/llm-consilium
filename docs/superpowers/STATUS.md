# LLM Consilium — project STATUS / handoff (as of 2026-07-24)

Durable state map so work survives a context compaction. Trust `git log`, the SDD ledger
(`.superpowers/sdd/progress.md`, git-ignored), and this doc over recollection.

## What it is
A VM-wide **free-LLM council** consulted by Claude Code via a user-scope MCP (`consilium`,
tools `ask`/`council`/`stats`), backed by a local LiteLLM proxy (`127.0.0.1:4000`). 3 layers:
compute (proxy) → council (orchestrator lib) → Claude integration (MCP). Core differentiator:
**privacy-tiering by provider free-tier train-policy** — `sensitive` prompts route to Tier-A
(no-train) only; `public` may use Tier-B.

## Phase map (all DONE unless noted)
- **0 Compute / 1 Council+MCP / 2a always-on / 2b rate-limit telemetry** — MERGED (PRs #1–#4).
- **2c Providers + robustness** — MERGED (PR #5). Pool 5→13 members (7 Tier-A incl. GitHub Models,
  6 Tier-B Mistral/SambaNova/NVIDIA); per-capability `scores` dossiers + `provider_family`; dynamic
  vendor-diverse council roster (auto / manual `members` / adaptive `size`); key-presence activation
  (keyless provider = dormant); LiteLLM native retry/cooldown/within-tier fallbacks. NVIDIA dormant
  (no key). Live-corrected IDs: `github/gpt-4.1-mini` (o-series unavailable), `sambanova/DeepSeek-V3.1`.
- **2d Council-quality ("full menu")** — MERGED (2d-1 #7, 2d-2 #8, 2d-3 #9). Aggregation modes:
  `mode` = None(auto vote/judge) | "vote" | "judge" | "peer-rank" | "debate".
  - 2d-1: `council/anonymize.py` code-names + shuffle; Fusion judge prompt; `AggregateResult` +
    categorical `confidence` (high/med/low).
  - 2d-2: `peer-rank` (members rank anonymized answers, mean-ordinal, self-vote excluded, pick-best
    verbatim) via `anonymize_pairs` owner-map.
  - 2d-3: `debate` (for/against/neutral stances + honesty guardrail + ≤2 CHALLENGE→REVISE rounds +
    Jaccard convergence early-exit + Fusion synth + confidence-as-rigor).
  - Helpers in `aggregate.py`: `_vote`/`_judge`/`_peer_rank`/`_debate`, `_jaccard`/
    `_mean_pairwise_jaccard`/`_parse_ranking`/`_parse_revision`.
- **2e Observability** — MERGED (PR #10). `council/runlog.py`: opt-in `CONSILIUM_LOG=1` → JSONL per
  council run to `~/.config/consilium/runs.jsonl`; content only when all-Tier-A, else redacted. For
  calibration on real projects (tune convergence 0.7, adaptive-K, mode choice, prompts).
- **MCP config-path hotfix** — MERGED (PR #12). `orchestrator.build` now uses an ABSOLUTE
  `DEFAULT_CONFIG_PATH` (from module location) so the user-scope MCP works from any project CWD
  (was relative → `Errno 2` from other dirs). Lesson: MCP runtime must never use CWD-relative paths.
- **Phase 3 Distribution** = cross-platform (Linux+Windows) Python CLI `python -m consilium <cmd>`
  (no bash); sub-waves 3a/3b/3c:
  - **3a init wizard** — MERGED (PR #11). `consilium/` package: `init` (hidden getpass key entry, 7
    providers, secure atomic `.env` write via mkstemp+os.replace — fixed TOCTOU + symlink-follow,
    live readiness ping). Modules: `env_file.py`, `providers.py`, `init.py`, `__main__.py`.
  - **3b runtime CLI** — MERGED (PR #13). `start`/`stop`/`status` (bg proxy + PID), `mcp-register`,
    `install-service` (systemd/Task-Sched), `doctor`; new `paths.py`/`service.py`/`setup.py`/`doctor.py`;
    de-hardcode remaining `/opt` (usage-rule.md → `mcp-register`; removed static deploy unit + superseded
    bash install scripts). Canonical launcher = `consilium start --foreground`.
  - **3c README/LICENSE/public** — MERGED (PR #14): `LICENSE` (MIT), `README.md` (privacy hook,
    Tier-A/B table, cross-platform install chain, usage/modes, architecture, privacy, credits), repo
    scrub (clean: no tracked secrets, no machine-specific runtime paths). **Repo is still PRIVATE** —
    `gh repo edit --visibility public` is USER-GATED (not run; pending explicit "make it public"). Before
    the flip, decide whether `docs/superpowers/` dev-process docs stay in the public repo.
- **3d Backlog-zero hardening** — on branch `phase-3d` (BURST format: 6 parallel worktree agents + fix
  wave). Closes ALL nine deferred-backlog items: 429 retry/backoff + Retry-After cap + served-200 usage
  accounting (client.py); aggregation timeout plumbed into peer-rank/debate + fan-out (aggregate/orchestrator);
  `_token_count` hardened against non-numeric tokens; mkstemp chmod cleanup (env_file); per-member `cost_usd`
  + multi-day `UsageStore.history` + `stats(days)` (usage/orchestrator/MCP, no schema migration); corrupt-DB,
  hermetic-unwritable-path, and None-answer-redaction tests. Gate: ruff clean, 209 passed. Spec+plan:
  `docs/superpowers/{specs,plans}/2026-07-24-phase-3d-*`.

## Branch / merge / deploy
- GitHub: private repo `Jama123321/llm-consilium`. `main` has everything through 3a + hotfix.
- **PR-merge gotcha:** don't stack a PR on another PR's branch with `--delete-branch` (GitHub closes
  the child, not retargets). Branch each sub-wave off `main`; merge with `--merge` (not squash).
- **Deployed live:** systemd `--user` `consilium-proxy` (active/enabled/linger) on :4000 (restarted
  onto the 2c 13-member config). MCP `consilium --scope user` (ask/council/stats). Usage rule in
  `~/.claude/CLAUDE.md`. Secrets in `~/.config/consilium/.env` (chmod 600). `usage.db`/`runs.jsonl` in
  `~/.config/consilium/`. **The running MCP uses the working-tree code** — a fresh MCP spawn (restart
  the Claude Code session) is needed to pick up code changes.

## Research (2026-07-14, in `docs/research/`)
- `prior-art-comparison-2026-07-14.md` — free-council+MCP is crowded; our edge = privacy-tiering.
- `borrow-map-2026-07-14.md` — borrows realized across 2c/2d (ai-council code-names/Fusion MIT copied-
  as-reimpl; PAL stance Apache reimpl; karpathy peer-rank & DUH convergence reimpl). Repo stays
  MIT-shareable (no verbatim third-party code; credit comments only).

## Deferred backlog (non-blocking)
- **Empty** — all prior items closed by Phase 3d (backlog-zero hardening, 2026-07-24): 429 retry/backoff
  + Retry-After cap, served-200 usage accounting, aggregation timeout plumbing (peer-rank/debate + fan-out),
  `_token_count` hardening, mkstemp chmod cleanup, cost tracking, multi-day history, and the corrupt-DB /
  hermetic-unwritable-path / None-answer-redaction test gaps. See the 3d spec+plan under
  `docs/superpowers/{specs,plans}/2026-07-24-phase-3d-*`.

## Next steps
1. ✅ 3a/3b/3c MERGED (PRs #11/#13/#14). 3d (backlog-zero) on `phase-3d` → PR → merge (user-gated).
2. **Go public** when the user says so: `gh repo edit Jama123321/llm-consilium --visibility public`
   (USER-GATED — never auto-run). Before the flip, decide whether `docs/superpowers/` process docs stay
   in the public repo. Optionally add a `consilium uninstall-service` + PyPI packaging later.
3. Optional: use the council + `CONSILIUM_LOG=1` on a real project to calibrate thresholds/prompts.
4. Backlog is now **empty** — 3d closed every deferred item.

Workflow discipline: brainstorm→spec→plan→SDD, all subagents on Opus, `ruff`+`pytest` gate,
PR-per-(sub)wave, no `Co-Authored-By`, no merge to `main` without explicit user OK.
