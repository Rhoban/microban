#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Make this robot's SD card ready to be copied to other robots (docs/sd_image.md), then power it off:
#   sudo bash systemd/prepare-image.sh [--keep-wifi] [--keep-ssh-keys] [--no-poweroff]
# - installs microban-firstboot (each copy grows its partition and gets its own machine-id, SSH host keys and
#   hostname microban-XXXX at its first boot);
# - Ethernet: a link-local address besides DHCP, so that a PC plugged directly
#   with a cable reaches the robot (tools/robot_wifi.sh), and the robot announces itself (mDNS: microban-XXXX.local);
# - removes the saved wifi networks and the authorized SSH keys (unless --keep-...), the logs, histories and caches.
# Run on the robot as root from the repo root.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run it with sudo"; exit 1; }
KEEP_WIFI=0; KEEP_KEYS=0; POWEROFF=1
for a in "$@"; do
    case "$a" in
        --keep-wifi) KEEP_WIFI=1 ;; --keep-ssh-keys) KEEP_KEYS=1 ;; --no-poweroff) POWEROFF=0 ;;
        *) echo "unknown option $a"; exit 1 ;;
    esac
done
REPO=$(cd "$(dirname "$0")/.." && pwd)
USER_NAME=${SUDO_USER:-radxa}
USER_HOME=$(getent passwd "$USER_NAME" | cut -d: -f6)

# first boot of each copy
install -m 755 "$REPO/systemd/microban-firstboot.sh" /usr/local/sbin/microban-firstboot
install -m 644 "$REPO/systemd/microban-firstboot.service" /etc/systemd/system/microban-firstboot.service
systemctl daemon-reload
systemctl enable microban-firstboot.service
touch /etc/microban-firstboot

# Ethernet: DHCP and link-local side by side (a direct cable to a PC); mDNS announces the robot and its SSH
"$REPO/systemd/setup-ethernet.sh"

# saved wifi networks
if [ "$KEEP_WIFI" = 0 ]; then
    nmcli -t -f NAME,TYPE con show | awk -F: '$2 == "802-11-wireless" {print $1}' | while read -r c; do
        echo "removing the wifi network $c"; nmcli con delete "$c" >/dev/null
    done
fi
# authorized SSH keys (access with the user's password)
if [ "$KEEP_KEYS" = 0 ]; then rm -f "$USER_HOME/.ssh/authorized_keys"; fi

# logs, histories, caches, DHCP leases
rm -f "$USER_HOME/.bash_history" /root/.bash_history "$USER_HOME/.python_history"
rm -rf "$USER_HOME/.cache/"* "$REPO/logs" "$REPO/recordings" "$REPO/move_options.json"
rm -f /var/lib/NetworkManager/*.lease /var/lib/dhcp/*.leases
apt-get clean
journalctl --rotate >/dev/null 2>&1; journalctl --vacuum-time=1s >/dev/null 2>&1
find /var/log -type f \( -name "*.gz" -o -name "*.[0-9]" -o -name "*.old" \) -delete
find /var/log -type f -exec truncate -s 0 {} +
fstrim -v / || true
sync

echo "Ready to be copied: power off, then copy the card (docs/sd_image.md)."
if [ "$POWEROFF" = 1 ]; then poweroff; fi
