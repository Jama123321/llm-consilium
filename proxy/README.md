# Consilium proxy (Phase 0)

Single OpenAI-compatible `/v1` on `127.0.0.1:4000` fronting 3 Tier-A providers.

## 1. Provision keys (once)
Copy the contract and fill real values (all free, no card):
```bash
mkdir -p ~/.config/consilium
cp .env.example ~/.config/consilium/.env
chmod 600 ~/.config/consilium/.env
# edit ~/.config/consilium/.env — see the comments for each console
```

## 2. Run the proxy
```bash
bash scripts/run-proxy.sh          # loads the env file, validates, launches on 127.0.0.1:4000
```
List the registered aliases:
```bash
curl -s -H "Authorization: Bearer $LITELLM_MASTER_KEY" http://127.0.0.1:4000/v1/models
```

## 3. Live health-check (in a second shell)
```bash
set -a; source ~/.config/consilium/.env; set +a
.venv/bin/python scripts/healthcheck.py
```
Prints `[PASS]/[FAIL]` for `/v1/models` and one completion per provider; exits 0 only if all pass. A model-id mismatch shows as a FAIL — fix the id in `proxy/config.yaml`.
