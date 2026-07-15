# Phase 3c — README + LICENSE + go public (design/spec)

> Status: prepared ahead (2026-07-14), pending user review at 3c start. Final sub-wave of
> Phase 3 (distribution), after 3a (init wizard) and 3b (runtime CLI).

## Business context

The council works, installs with `python -m consilium init` / `start` / `mcp-register`, and
is privacy-safe. 3c makes it *shareable*: an MIT `LICENSE`, a `README` that leads with the
privacy differentiator and gives a colleague a copy-paste install-and-use path, a scrub of
any machine-specific references, and finally flipping the GitHub repo to public. This is the
"anyone can clone and run it" milestone.

## Goal

Add `LICENSE` (MIT), a positioning `README.md`, scrub committed files of machine-specific /
sensitive references, and flip the repo to public — the public flip gated on explicit user
confirmation.

## Global Constraints (verbatim)

- **No secrets, ever, in committed files.** Scrub before publishing; `.env`/`*.key` stay
  gitignored (already).
- **Repo stays MIT-shareable:** we reimplemented borrowed designs (no verbatim third-party
  code); README credits the prior-art ideas as courtesy. MIT license, one copyright line.
- **Publishing is user-gated:** `gh repo edit --visibility public` is outward-facing and hard
  to reverse — it is a final step the USER runs (or I run only on explicit "make it public
  now" confirmation). The plan never auto-publishes.
- **Accuracy:** every command in the README must be the real, current interface (`python -m
  consilium init/start/status/mcp-register/install-service/doctor`; MCP tools ask/council/stats;
  council `mode` = vote/judge/peer-rank/debate; `sensitivity` sensitive/public). No stale
  `/opt/...` paths (3b de-hardcoded them).
- Docs-only wave: no code changes, so `ruff`+`pytest` stay trivially green; the quality gate is
  a content review (README accuracy) + a scrub verification. Commits English imperative, no
  `Co-Authored-By`. Branch `phase-3c` (off `main`, after 3b merges).

## 1. `LICENSE` (MIT)

Standard MIT text, `Copyright (c) 2026 <repo owner>`. Owner string confirmed with the user at
3c start (default: the GitHub account name).

## 2. `README.md`

Sections, in order:
1. **Title + one-line hook** — "A privacy-tiered council of *free* cloud LLMs for Claude Code —
   private code never reaches a provider that trains on it."
2. **Why / differentiation** — free-council + MCP is crowded; the edge is privacy-tiering by
   provider free-tier train-policy (Tier-A no-train vs Tier-B), a first-class gate on every call.
3. **Providers table** — Tier-A (Cerebras, Groq, Cloudflare, GitHub Models) vs Tier-B (Mistral,
   SambaNova, NVIDIA NIM), with the "tier follows the inference provider" note.
4. **Install (cross-platform, no bash)** — clone → `python -m consilium init` (keys + readiness)
   → `consilium start` (or `install-service` for autostart) → `consilium mcp-register` → restart
   Claude Code → `consilium doctor` to verify. Note the `.venv`/deps prerequisite.
5. **Usage** — the MCP tools `ask` / `council` / `stats`; council `mode` (auto | vote | judge |
   peer-rank | debate) and `sensitivity` (sensitive default | public); when to use each; the
   `CONSILIUM_LOG=1` calibration log.
6. **Architecture** — the 3 layers (proxy → orchestrator → MCP), one diagram/paragraph.
7. **Privacy model** — the hard rule (sensitive → Tier-A only; secrets never sent; Tier-B =
   public only), and how key-presence activation degrades gracefully.
8. **Credits / prior art** — the reimplemented design ideas (ai-council MIT, FreeLLMAPI MIT, PAL
   Apache, DUH design), reimplemented not copied. **License: MIT.**

Lead with the hook; keep it skimmable; every command copy-pasteable and current.

## 3. Scrub + go-public

- **Scrub:** grep committed files for machine-specific / sensitive strings — the concrete home
  path (`/home/root1`, `root1`), any residual absolute `/opt/...`, VM-specific hostnames, real
  key fragments. Fix any hit (generalize to `~`/relative/placeholder). `docs/` narrative that
  references "this VM" is fine as project history but must not leak secrets.
- **Verify gitignore** covers `.env`, `*.key`, `__pycache__`, venvs, `.superpowers/` scratch.
- **Go public (USER-gated):** on explicit confirmation, `gh repo edit --visibility public`.
  Until then, leave private. The plan documents the command but does not run it.

## 4. Out of scope
- Any code change (3b delivered the CLI). Packaging to PyPI / `pip install`. CI setup. A logo.
- Automating the public flip without confirmation.

## 5. Files
- `LICENSE` — NEW.
- `README.md` — NEW (repo root).
- Possibly minor scrub edits to existing `docs/` / `scripts/` if grep finds machine-specific refs.
