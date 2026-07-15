# Phase 3c — README + LICENSE + go public Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Docs wave — review-driven (no TDD; the gate is content accuracy + a scrub, plus the always-green `ruff`+`pytest`). Steps use checkbox (`- [ ]`) syntax.

**Goal:** Add `LICENSE` (MIT) and a positioning `README.md`, scrub machine-specific references, and prepare (user-gated) the flip to a public repo.

**Architecture:** Pure documentation + repo config. No code change → `ruff`/`pytest` stay green. The public flip is a final manual, user-confirmed step.

**Tech Stack:** Markdown, git, `gh`.

## Global Constraints

- No secrets in committed files; scrub before publishing. `.env`/`*.key`/venvs/`.superpowers/` stay gitignored.
- Every README command must be the real current interface (`python -m consilium init/start/status/mcp-register/install-service/doctor`; MCP `ask`/`council`/`stats`; council `mode`=vote/judge/peer-rank/debate; `sensitivity`=sensitive/public). No stale `/opt/...`.
- Repo stays MIT-shareable (borrows reimplemented, credited as courtesy). MIT license, one copyright line.
- **`gh repo edit --visibility public` is USER-gated** — documented, never auto-run.
- Commits English imperative, no `Co-Authored-By`. Branch `phase-3c` (off `main`, after 3b merges).

## File map
- `LICENSE` — NEW. `README.md` — NEW (repo root). Minor scrub edits to `docs/`/`scripts/` if grep hits.

---

### Task 1: LICENSE (MIT)

**Files:** Create `LICENSE`.

- [ ] **Step 1: Confirm the copyright owner** — default the GitHub account (`Jama123321`); ask the user if they want a real name/org.

- [ ] **Step 2: Write `LICENSE`** (verbatim MIT, fill the owner):

```
MIT License

Copyright (c) 2026 <OWNER>

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 3: Commit** — `git add LICENSE && git commit -m "docs(3c): add MIT license"`

---

### Task 2: README.md

**Files:** Create `README.md`.

Write a skimmable README leading with the privacy hook. Sections (use the EXACT commands/values below — prose may be authored, structure and commands are fixed):

- [ ] **Step 1: Title + hook** — e.g. `# LLM Consilium` then: "A privacy-tiered council of *free* cloud LLMs, on tap inside Claude Code. Private code never reaches a provider that trains on it."

- [ ] **Step 2: Why / differentiation** — 2-3 sentences: free-council+MCP is crowded; the edge is **privacy-tiering by provider free-tier train-policy** (Tier-A no-train vs Tier-B), enforced as a first-class gate on every call.

- [ ] **Step 3: Providers table**

```markdown
| Tier | Providers | Use |
|------|-----------|-----|
| **A** (no-train) | Cerebras, Groq, Cloudflare Workers AI, GitHub Models | any prompt (incl. private code) |
| **B** (trains/undocumented) | Mistral, SambaNova, NVIDIA NIM | `public` prompts only |
```
Note: tier follows the **inference provider**, not the weights' origin. A provider without a key stays dormant (key-presence activation).

- [ ] **Step 4: Install (cross-platform, no bash)**

```bash
git clone https://github.com/<owner>/llm-consilium && cd llm-consilium
python -m venv .venv && . .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt                      # or the project's install
python -m consilium init                             # enter the free keys you have -> readiness table
python -m consilium start                            # background proxy (or: install-service for autostart)
python -m consilium mcp-register                     # wire into Claude Code (restart Claude Code after)
python -m consilium doctor                           # verify keys / proxy / MCP
```
(If `requirements.txt` isn't the real install path, use the project's actual one — verify before writing.)

- [ ] **Step 5: Usage** — the MCP tools:
  - `ask(prompt, model?, capability?, sensitivity?)` — one best-fit model (auto-routed).
  - `council(prompt, sensitivity?, members?, size?, mode?)` — fan out + aggregate. `mode` = omit(auto vote/judge) | `"vote"` | `"judge"` | `"peer-rank"` | `"debate"`.
  - `stats()` — per-member usage vs caps.
  - `sensitivity` = `"sensitive"` (default, Tier-A only) | `"public"` (adds Tier-B). Optional `CONSILIUM_LOG=1` → `~/.config/consilium/runs.jsonl` for calibration.

- [ ] **Step 6: Architecture + Privacy + Credits**
  - Architecture: 3 layers — LiteLLM proxy (compute) → orchestrator (council: gate, fan-out, modes) → user-scope MCP (Claude Code integration).
  - Privacy model: `sensitive` → Tier-A only; secrets never sent to any free tier; Tier-B = public only; graceful degradation when keys are missing.
  - Credits: reimplemented design ideas from ai-council-mcp (MIT), FreeLLMAPI (MIT), PAL/zen (Apache), DUH (design) — reimplemented, not copied. **License: MIT.**

- [ ] **Step 7: Commit** — `git add README.md && git commit -m "docs(3c): add README leading with the privacy hook"`

---

### Task 3: Scrub + publish-prep

**Files:** possibly `docs/`, `scripts/`, `.gitignore`.

- [ ] **Step 1: Scrub for machine-specific / sensitive strings**

```bash
grep -rnI --exclude-dir=.git --exclude-dir=.venv -e "/home/root1" -e "root1" -e "/opt/claude-projects" . | grep -v "\.superpowers/"
```
Fix any hit in tracked files: generalize the home path to `~`, absolute `/opt/...` to relative/derived, remove VM-specific hostnames. `docs/` narrative that says "this VM" as history is acceptable if it leaks nothing sensitive; prefer generalizing.

- [ ] **Step 2: Verify no real secrets are tracked**

```bash
git ls-files | grep -Ei "\.env$|\.key$" ; echo "(expect no output)"
grep -rnI --exclude-dir=.git -e "sk-" -e "csk-" -e "gsk_" --include="*.py" --include="*.md" --include="*.yaml" . | grep -vE "sk-\{|token_hex|example|placeholder|<|test|mask|scan"
```
Confirm only placeholders/examples appear — no live key material. Confirm `.gitignore` covers `.env`, `*.key`, `__pycache__/`, venvs, `.superpowers/`.

- [ ] **Step 3: Commit any scrub fixes** — `git add -A && git commit -m "docs(3c): scrub machine-specific references before publishing"` (skip if nothing to fix).

- [ ] **Step 4: Go public — USER-GATED (do NOT run without explicit confirmation)**

Document, and run ONLY when the user says "make it public now":
```bash
gh repo edit <owner>/llm-consilium --visibility public --accept-visibility-change-consequences
```
Until then, leave the repo private. This is the one irreversible, outward-facing step.

---

## Self-review

**Spec coverage:** LICENSE (MIT) → T1; README (hook, providers, install, usage, architecture, privacy, credits) → T2; scrub + gitignore verify + user-gated public flip → T3. Every README command is the real current interface (3a/3b), no stale `/opt`. Public flip is user-gated, never auto-run.

**Placeholder scan:** the `<OWNER>` / `<owner>` and "verify the real install path" are deliberate execution-time confirmations (owner name, install command) — resolve at 3c start, not silent gaps.

**Consistency:** commands match the CLI shipped in 3a (`init`) + 3b (`start`/`status`/`mcp-register`/`install-service`/`doctor`); MCP tool signatures match `consilium_mcp/server.py` (ask/council with mode/members/size, stats).
