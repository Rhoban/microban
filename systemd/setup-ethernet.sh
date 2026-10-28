#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
#
# The robot's Ethernet port: a link-local address (169.254.x.x, for a cable straight to a PC) and DHCP (a cable to a
# network); mDNS (avahi) announces the robot as <hostname>.local with its SSH service, so a
# PC on the same cable finds it (tools/robot_wifi.sh). Run on the robot as root (systemd/prepare-image.sh does it).
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run it with sudo"; exit 1; }

dev=$(ls /sys/class/net | grep -E '^(en|eth)' | head -1)
con=$(nmcli -t -f NAME,TYPE con show | awk -F: '$2 == "802-3-ethernet" {print $1; exit}')
if [ -z "$con" ]; then
    con="Wired connection 1"
    nmcli con add type ethernet ifname "$dev" con-name "$con" >/dev/null
fi
# DHCP and a link-local address side by side (NetworkManager 1.42 has no "fallback"); DHCP may fail: the cable then
# keeps its link-local address, and DHCP goes on trying (a network plugged later gives its address too)
nmcli con modify "$con" ipv4.method auto ipv4.link-local enabled ipv4.may-fail yes ipv4.dhcp-timeout infinity \
    ipv6.method link-local connection.autoconnect yes connection.autoconnect-retries 0
echo "Ethernet ($dev, \"$con\"): link-local address (169.254.x.x) and DHCP"

mkdir -p /etc/avahi/services
cat > /etc/avahi/services/ssh.service <<'EOF'
<?xml version="1.0" standalone='no'?>
<!DOCTYPE service-group SYSTEM "avahi-service.dtd">
<service-group>
  <name replace-wildcards="yes">%h</name>
  <service><type>_ssh._tcp</type><port>22</port></service>
</service-group>
EOF
systemctl restart avahi-daemon
echo "mDNS: $(hostname).local announced with its SSH service"
