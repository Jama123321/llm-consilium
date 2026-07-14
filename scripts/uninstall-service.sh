#!/usr/bin/env bash
# Stop and remove the Consilium proxy systemd --user service.
set -euo pipefail
systemctl --user disable --now consilium-proxy.service 2>/dev/null || true
rm -f "$HOME/.config/systemd/user/consilium-proxy.service"
systemctl --user daemon-reload
echo "consilium-proxy uninstalled. (Linger unchanged: loginctl disable-linger $USER to revert.)"
