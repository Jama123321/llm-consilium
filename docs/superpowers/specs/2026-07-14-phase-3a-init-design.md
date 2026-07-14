# Phase 3a — `consilium init` key wizard (design/spec)

> Status: approved for planning (2026-07-14). Next: writing-plans.
> First sub-wave of Phase 3 (distribution). 3a = key wizard; then 3b = runtime CLI
> (start/stop/status/mcp-register/doctor) + de-hardcoded paths; then 3c = README/LICENSE/go-public.

## Business context

To share consilium, a colleague must supply their own free-tier API keys. Today that means
hand-editing `~/.config/consilium/.env` from a comment template — error-prone and opaque
(no feedback on whether a key actually works). `consilium init` is a cross-platform Python
wizard that collects keys interactively, writes the env file safely and idempotently, and
**live-pings each configured provider** so the colleague sees a green/red readiness table
before wiring anything into Claude Code. Providers whose key is skipped stay dormant (the
key-presence activation from 2c), so a partial key set yields a working subset, not errors.

## Goal

A `consilium` Python package runnable as `python -m consilium init` (cross-platform, no
bash) that: prompts per provider (hidden key entry), generates the master key if absent,
writes `~/.config/consilium/.env` idempotently (chmod 600 on POSIX), live-pings each
configured provider, and prints a readiness table.

## Global Constraints (verbatim, apply to every task)

- **Secrets discipline (the core rule):** keys are read with hidden input (`getpass`),
  **never echoed, never logged, never printed back**. They are written only to
  `~/.config/consilium/.env` and sent only to *their own* provider's endpoint during the
  ping (never to another provider). The wizard displays only masked status
  (e.g. `set (sk-…last4)` or `not set`), never the full value.
- **Cross-platform:** pure Python + stdlib + `httpx` (already a dep). No bash, no
  POSIX-only calls without a guard. `chmod 600` applied on POSIX; on Windows, skipped with
  a printed note (rely on the user profile's default ACL).
- **Idempotent:** re-running preserves every existing `KEY=VALUE` in the file (known and
  unknown), updating only the keys the user (re)enters; pressing Enter keeps the current
  value (or skips if unset).
- **Testable:** interactive input and the network ping are injected (dependency injection),
  so tests script them — no real prompts or network in tests.
- **Ping is non-fatal:** a red ping never aborts init; it's informational. The wizard always
  finishes by writing the env file.
- Add `"consilium"` to `pyproject.toml` `[tool.ruff.lint.isort] known-first-party`.
- Python 3.10+; `ruff check .` clean + `pytest -q` green. Commits English imperative, no
  `Co-Authored-By`. Branch `phase-3a-init`.

## 1. Provider registry — `consilium/providers.py`

A static list of the free providers, decoupled from `proxy/config.yaml` (which is the
LiteLLM model list; the wizard needs provider-level metadata + signup URLs the config lacks).

```python
@dataclass(frozen=True)
class Provider:
    key: str            # provider_family, e.g. "cerebras"
    name: str           # display, e.g. "Cerebras"
    tier: str           # "A" | "B"
    env_vars: tuple[str, ...]   # secrets to collect (usually 1; Cloudflare has 2)
    signup: str         # human where-to-get-a-key hint (URL + steps)
    ping_base_url: str  # OpenAI-compatible base for the readiness ping
    ping_model: str     # a cheap current model id for the 1-token ping
```

`PROVIDERS: tuple[Provider, ...]` covers the 7: cerebras, groq, cloudflare (env_vars
`CLOUDFLARE_API_TOKEN` + `CLOUDFLARE_API_BASE`; its `ping_base_url` is taken from the
`CLOUDFLARE_API_BASE` value at ping time), github, mistral, sambanova, nvidia. `ping_model`
uses the ids verified live in 2c (e.g. github → `openai/gpt-4.1-mini`, sambanova →
`Meta-Llama-3.3-70B-Instruct`). IDs may drift — a red ping is informational, not fatal.

## 2. Env-file read/write — `consilium/env_file.py`

- `DEFAULT_ENV_PATH = Path.home() / ".config" / "consilium" / ".env"`.
- `load(path) -> dict[str, str]` — parse `KEY=VALUE` lines (skip blanks/comments), return all
  pairs (known and unknown), preserving nothing else.
- `write(path, values: dict[str, str]) -> None` — write a clean, templated file: a header
  comment, then the keys grouped Tier-A / Tier-B / master with brief per-provider comments;
  emits **every** key in `values` (so unknown keys are preserved by the caller passing them
  through). Creates the parent dir; `chmod 0o600` on POSIX (guarded by `os.name == "posix"`).

## 3. The wizard — `consilium/init.py`

- `mask(value: str) -> str` — `"set (…last4)"` for non-empty, `"not set"` for empty. Never
  returns the full secret.
- `run(*, env_path=DEFAULT_ENV_PATH, prompt=getpass.getpass, echo=print, ping=live_ping) -> int`:
  1. `existing = env_file.load(env_path)`.
  2. For each `Provider` and each of its `env_vars`: show name, tier, signup, and the current
     masked status; prompt (hidden) — a non-empty entry sets/updates it, empty keeps the
     existing value (or leaves unset).
  3. Ensure `LITELLM_MASTER_KEY`: if absent, generate `f"sk-{secrets.token_hex(24)}"`.
  4. `env_file.write(env_path, merged)` where `merged = {**existing, **collected}` (unknown
     keys preserved).
  5. For each provider whose required `env_vars` are all now present, call
     `ping(provider, merged)` → a `PingResult(ok: bool, detail: str)`; build a readiness table
     (🟢 ok / 🔴 failed / ⚪ dormant-no-key) and `echo` it.
  6. Return 0.
- `live_ping(provider, env) -> PingResult` — `httpx.post(f"{base}/chat/completions", json={
  "model": provider.ping_model, "messages": [{"role": "user", "content": "ping"}],
  "max_tokens": 1}, headers={"Authorization": f"Bearer {key}"}, timeout=15)`; 2xx → ok;
  else `ok=False` with the status/reason. Cloudflare's `base` comes from the
  `CLOUDFLARE_API_BASE` value. Never logs the key.

## 4. Entrypoint — `consilium/__main__.py`, `consilium/__init__.py`

- `consilium/__init__.py` — empty (package marker).
- `consilium/__main__.py` — minimal dispatch: `init` → `consilium.init.run()`; unknown/absent
  → usage message. (`start`/`stop`/`status`/`doctor`/`mcp-register` are added in 3b.)
- Invocable as `python -m consilium init` from the repo root (pythonpath already `["."]`).

## 5. Testing

- **env_file**: `load` parses KEY=VALUE, skips comments/blanks, returns unknown keys too;
  `write` round-trips (`load(write(x)) == x`), preserves unknown keys, emits master + tiers;
  POSIX chmod path guarded (assert mode 0o600 on posix via `tmp_path`).
- **providers**: registry sanity — 7 providers, each with ≥1 env var, valid tier, non-empty
  signup/ping fields; Cloudflare has both `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_API_BASE`.
- **mask**: hides the secret (last-4 only; empty → "not set"); never returns the full value.
- **run** (injected `prompt`/`echo`/`ping`, `tmp_path` env): scripted keys are written;
  empty entry keeps an existing value; master key generated when absent and preserved when
  present; unknown pre-existing key preserved; readiness table reflects the injected ping
  results (green/red/dormant); a red ping does not abort (return 0, file still written); the
  full secret never appears in captured `echo` output.

## 6. Out of scope (explicit)

- `consilium start`/`stop`/`status`/`doctor`/`mcp-register`, de-hardcoding runtime paths,
  systemd/Task-Scheduler → **3b**.
- README / LICENSE / making the repo public → **3c**.
- Editing `proxy/config.yaml` or the council/MCP code — untouched here.

## 7. Files

- `consilium/__init__.py`, `consilium/__main__.py`, `consilium/providers.py`,
  `consilium/env_file.py`, `consilium/init.py` — all NEW.
- `pyproject.toml` — add `"consilium"` to `known-first-party`.
- Tests: `tests/test_env_file.py`, `tests/test_providers.py`, `tests/test_init.py` — NEW.
