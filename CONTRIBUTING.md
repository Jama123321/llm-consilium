# Contributing to LLM Consilium

Thanks for your interest in improving LLM Consilium. This guide covers how to set
up a dev environment, the quality gate every change must pass, the design-first
workflow, and the rules for commits and privacy.

## Development setup

Create a virtual environment and install the package with its dev extras
(editable install):

```bash
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
```

## The gate — required before anything is "done"

Both of these must be green:

```bash
ruff check .
.venv/bin/python -m pytest
```

CI enforces **both** on Python **3.10, 3.11, 3.12, and 3.13**. A change that
fails lint or tests will not be merged. Run the gate locally before you push.

## Workflow — features start from a design

This project uses a **brainstorm → spec → plan → subagent-driven execution**
workflow. Design and specification come **before** code:

1. **Brainstorm** the change with the maintainer and agree on the design.
2. Write a **spec** and a task-by-task **plan** (see `docs/superpowers/`).
3. **Execute** the plan via subagent-driven development (fresh subagent per task,
   review, then the gate).

Every feature starts from a design — please do not open a large PR without first
aligning on the approach.

## Commit and branch rules

- Write commit subjects in **English, imperative mood** (e.g. `docs: add security policy`).
- **Never** add a `Co-Authored-By` trailer.
- **Branch off `main`** for your work; do not commit directly to `main`.
- **Never merge to `main` without the maintainer's explicit OK.**
- **Never** use `--force` / force-push, and never `--no-verify`.

## Privacy rule — non-negotiable

- **Never send secrets, `.env` files, or credentials to any free tier** — not even
  a Tier-A (no-train) provider. Strip sensitive data before it can reach the council.
- **Never commit `~/.config/consilium/.env`** (or any other secrets file). The
  runtime env lives outside the repo by design.

Thanks for helping keep the council private, correct, and free.
