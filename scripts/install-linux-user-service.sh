#!/bin/sh
# Optional user service; run manually, never installed by the project automatically.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
python=$(command -v python3)
case "$root" in *'"'*|*'%'*|*'\'*) echo 'Use a path without double quotes, percent signs or backslashes for this service installer.' >&2; exit 1;; esac
mkdir -p "$HOME/.config/systemd/user"
cat > "$HOME/.config/systemd/user/agent-hub-private.service" <<UNIT
[Unit]
Description=Agent Hub Private local coordinator
After=default.target
[Service]
Type=simple
WorkingDirectory="$root"
ExecStart="$python" "$root/hub.py" --home "$root/data" daemon
Restart=on-failure
RestartSec=10
[Install]
WantedBy=default.target
UNIT
systemctl --user daemon-reload
systemctl --user enable --now agent-hub-private.service
