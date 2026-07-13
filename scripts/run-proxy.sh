#!/usr/bin/env bash
# Load Consilium secrets, validate them, and launch the LiteLLM proxy on localhost.
set -euo pipefail

ENV_FILE="${CONSILIUM_ENV_FILE:-$HOME/.config/consilium/.env}"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

required=(CEREBRAS_API_KEY GROQ_API_KEY CLOUDFLARE_API_TOKEN CLOUDFLARE_API_BASE LITELLM_MASTER_KEY)
missing=()
for var in "${required[@]}"; do
  if [[ -z "${!var:-}" ]]; then
    missing+=("$var")
  fi
done
if (( ${#missing[@]} > 0 )); then
  echo "ERROR: missing required env vars: ${missing[*]}" >&2
  exit 1
fi

if [[ -n "${CONSILIUM_CHECK_ONLY:-}" ]]; then
  echo "OK: all required env vars present (check-only, not launching)"
  exit 0
fi

CONFIG="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/proxy/config.yaml"
exec litellm --config "$CONFIG" --host 127.0.0.1 --port 4000
