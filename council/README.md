# Council orchestrator (Phase 1)

`ask` (one best-fit model) and `council` (fan-out + adaptive aggregate) over the
Phase-0 proxy, exposed as the `consilium` MCP server.

## Live smoke (proxy must be up)
```bash
bash scripts/run-proxy.sh            # terminal 1
# terminal 2:
set -a; source ~/.config/consilium/.env; set +a
.venv/bin/python scripts/council-smoke.py
```

## Register the MCP tools
See `docs/usage-rule.md` for the `claude mcp add --scope user` command and the
`~/.claude/CLAUDE.md` protocol block.
