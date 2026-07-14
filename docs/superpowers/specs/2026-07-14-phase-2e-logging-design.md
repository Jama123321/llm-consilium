# Phase 2e — observability logging (design)

**Goal:** persist each `council` run as one JSON line for later calibration of
confidence/mode/roster quality against outcomes.

- **Opt-in flag:** logging is off unless `CONSILIUM_LOG=1` (or `RunLog(..., enabled=True)`
  is passed explicitly). Disabled → nothing is written.
- **Privacy redaction rule:** if any chosen member is Tier-B, the run is redacted —
  `prompt`/`answer` and each per-member `answer` are nulled and replaced with a
  `*_len` length field; `redacted:true` is stamped. All-Tier-A runs keep content
  (`redacted:false`). This mirrors the council's own privacy gate.
- **JSONL location:** `~/.config/consilium/runs.jsonl` (append-only, one object per line).
- **Council-only scope:** only `council` runs are logged, never `ask`.
- **Best-effort:** logging never raises into a call — parent-dir creation and write
  failures (`OSError`) are swallowed. Each entry carries a UTC `ts`.
