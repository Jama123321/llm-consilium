#!/usr/bin/env bash
# Install and start the Consilium proxy as a systemd --user service (always-on).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_SRC="$REPO_ROOT/deploy/consilium-proxy.service"
UNIT_DIR="$HOME/.config/systemd/user"
UNIT_DST="$UNIT_DIR/consilium-proxy.service"

if [[ ! -f "$UNIT_SRC" ]]; then
  echo "ERROR: unit file not found: $UNIT_SRC" >&2
  exit 1
fi

# Free port 4000 from any manually-started proxy before systemd takes over.
pkill -f "litellm --config" 2>/dev/null || true

mkdir -p "$UNIT_DIR"
cp "$UNIT_SRC" "$UNIT_DST"
systemctl --user daemon-reload
systemctl --user enable --now consilium-proxy.service

if loginctl enable-linger "$USER" 2>/dev/null; then
  echo "linger enabled (service survives logout/reboot)"
else
  echo "note: could not enable-linger; service runs while you are logged in"
fi

echo "--- status ---"
systemctl --user --no-pager status consilium-proxy.service | head -12 || true
