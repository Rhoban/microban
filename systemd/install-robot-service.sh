#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Install (or remove, with --uninstall) the robot service: the control loop (src/main.py) starts at boot, torque off
# until a move is launched, and streams to the dashboard (`make dashboard HOST=<robot>` on a PC). Without a
# terminal it takes a gamepad whenever one connects, otherwise the dashboard starts the moves.
# Run on the robot as root from the repo root (make robot-service-enable does it):
#   sudo bash systemd/install-robot-service.sh
set -euo pipefail

UNIT=/etc/systemd/system/microban.service
SUDOERS=/etc/sudoers.d/021_microban-service

if [[ "${1:-}" == "--uninstall" ]]; then
    systemctl disable --now microban.service 2>/dev/null || true
    rm -f "$UNIT" "$SUDOERS"
    systemctl daemon-reload
    echo "Robot service removed."
    exit 0
fi

USER_NAME=${SUDO_USER:-$(whoami)}
REPO=$(cd "$(dirname "$0")/.." && pwd)

# `make run` / `make robot-service-*` stop and start it over SSH without a password
cat > "$SUDOERS" <<EOS
%sudo ALL=(root) NOPASSWD: /usr/bin/systemctl start microban.service, /usr/bin/systemctl stop microban.service, /usr/bin/systemctl restart microban.service
EOS
chmod 440 "$SUDOERS"
visudo -cf "$SUDOERS"

cat > "$UNIT" <<EOS
[Unit]
Description=Microban control loop (torque off until a move is launched; dashboard link)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER_NAME
WorkingDirectory=$REPO
Environment=PYTHONPATH=$REPO/src
ExecStart=$REPO/.venv/bin/python -u src/main.py
# a crash restarts it; a normal stop (make stop, q) does not
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOS

systemctl daemon-reload
systemctl enable --now microban.service
echo "Robot service installed and started (user=$USER_NAME, repo=$REPO): it starts at every boot."
echo "On a PC: make dashboard HOST=<robot>. Logs: make robot-service-logs."
