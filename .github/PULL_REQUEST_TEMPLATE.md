## Summary

<!-- Why this change? What problem does it solve for the council? -->

## What changed

<!-- The concrete changes: files, behavior, interfaces. -->

-

## Testing

<!-- Paste the gate output (both must be green). -->

```
$ ruff check .

$ .venv/bin/python -m pytest
```

## Checklist

- [ ] `ruff check .` is clean and `.venv/bin/python -m pytest` is green (the gate).
- [ ] Commit subjects are English imperative with **no `Co-Authored-By` trailer**.
- [ ] Branched off `main`; not merging to `main` without the maintainer's OK.
- [ ] **No secrets / `.env` / credentials committed** (nothing under `~/.config/consilium/`).
- [ ] Privacy respected: no sensitive data routed to a free tier.
