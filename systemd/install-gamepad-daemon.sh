#!/usr/bin/env bash
# Install (or remove, with --uninstall) the opt-in headless gamepad launcher service.
# Run on the Pi as root from the repo root, e.g.:
#   sudo bash systemd/install-gamepad-daemon.sh
# Paths and the service user are derived from this script's location and $SUDO_USER,
# so it keeps working even if the account was renamed.
set -euo pipefail

UNIT=/etc/systemd/system/microban-gamepad.service
SUDOERS=/etc/sudoers.d/020_microban-rfkill

if [[ "${1:-}" == "--uninstall" ]]; then
    systemctl disable --now microban-gamepad.service 2>/dev/null || true
    rm -f "$UNIT" "$SUDOERS"
    systemctl daemon-reload
    rfkill unblock wifi 2>/dev/null || true
    echo "Headless gamepad service removed."
    exit 0
fi

USER_NAME=${SUDO_USER:-$(whoami)}
REPO=$(cd "$(dirname "$0")/.." && pwd)

# Let the daemon (running as $USER_NAME, in the sudo group) toggle Wi-Fi without a password.
cat > "$SUDOERS" <<EOF
%sudo ALL=(root) NOPASSWD: /usr/sbin/rfkill block wifi, /usr/sbin/rfkill unblock wifi
EOF
chmod 440 "$SUDOERS"
visudo -cf "$SUDOERS"

cat > "$UNIT" <<EOF
[Unit]
Description=Microban headless gamepad launcher
After=bluetooth.target

[Service]
Type=simple
User=$USER_NAME
WorkingDirectory=$REPO
Environment=PYTHONPATH=$REPO/src
ExecStart=$REPO/.venv/bin/python -u src/gamepad_daemon.py
Restart=on-failure
RestartSec=2
ExecStopPost=/usr/bin/sudo /usr/sbin/rfkill unblock wifi

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now microban-gamepad.service
echo "Headless gamepad service installed and started (user=$USER_NAME, repo=$REPO)."
echo "Connect the controller and hold START 2s to launch; press B to stop."
