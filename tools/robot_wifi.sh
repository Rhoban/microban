#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Add a wifi network to a robot reached through an Ethernet cable plugged straight into this PC (docs/sd_image.md).
#
#   tools/robot_wifi.sh                         # finds the robot (mDNS: microban-XXXX.local), asks the network
#   tools/robot_wifi.sh microban-1a2b.local     # or give it
#   tools/robot_wifi.sh --direct enp3s0         # Linux: first give this Ethernet port a link-local address
#   tools/robot_wifi.sh --list                  # the robot's saved networks and its addresses
#
# The robot's Ethernet always has a link-local address (169.254.x.x), besides DHCP. macOS and Windows do the same;
# a Linux PC with NetworkManager needs --direct <its Ethernet port> once (a "microban-direct" connection).
# SSH asks the robot's password (user radxa) unless your key is installed (ssh-copy-id radxa@<robot>).
set -euo pipefail

ROBOT=""; DIRECT=""; LIST=0
while [ $# -gt 0 ]; do
    case "$1" in
        --direct) DIRECT=$2; shift ;;
        --list) LIST=1 ;;
        -h|--help) sed -n '4,13p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) ROBOT=$1 ;;
    esac
    shift
done

if [ -n "$DIRECT" ]; then
    nmcli con delete microban-direct >/dev/null 2>&1 || true
    nmcli con add type ethernet ifname "$DIRECT" con-name microban-direct ipv4.method link-local \
        ipv6.method link-local connection.autoconnect no >/dev/null
    nmcli con up microban-direct >/dev/null
    echo "$DIRECT: link-local address for the robot's cable (nmcli con down microban-direct to undo)"
    sleep 5
fi

if [ -z "$ROBOT" ]; then
    echo "Looking for the robot (mDNS, 15 s at most)..."
    names=""
    for _ in $(seq 5); do
        if command -v avahi-browse >/dev/null; then
            names=$(avahi-browse -tpr _ssh._tcp 2>/dev/null | awk -F';' '$1 == "=" && $7 ~ /^microban-/ {print $7}' | sort -u)
        elif command -v dns-sd >/dev/null; then                        # macOS
            names=$( (dns-sd -B _ssh._tcp & sleep 3; kill $! 2>/dev/null) | awk '/microban-/ {print $NF".local"}' | sort -u)
        else
            echo "No mDNS browser: sudo apt install avahi-utils (Linux), or give the robot: tools/robot_wifi.sh microban-1a2b.local"; exit 1
        fi
        [ -n "$names" ] && break
        sleep 3
    done
    [ -n "$names" ] || { echo "No robot found: is the cable plugged in, the robot on for 1 min (Linux PC: --direct <port>)?"; exit 1; }
    if [ "$(echo "$names" | wc -l)" -gt 1 ]; then
        echo "Several robots:"; echo "$names"; echo "give one: tools/robot_wifi.sh <name>"; exit 1
    fi
    ROBOT=$names
fi
echo "Robot: $ROBOT"
SSH=(ssh -o StrictHostKeyChecking=accept-new "radxa@$ROBOT")

if [ "$LIST" = 1 ]; then
    "${SSH[@]}" 'nmcli -t -f NAME,TYPE con show | grep wireless | cut -d: -f1; ip -br -4 addr | grep -v "^lo"'
    exit 0
fi

echo "Wifi networks the robot sees:"
"${SSH[@]}" 'sudo nmcli dev wifi rescan 2>/dev/null; sleep 3; nmcli -f SSID,SIGNAL,SECURITY dev wifi list | head -15'
read -r -p "Network (SSID): " ssid
read -r -s -p "Password (empty for an open network): " pw; echo
# the password goes through SSH's input, not the command line
printf '%s\n%s\n' "$ssid" "$pw" | "${SSH[@]}" 'read -r ssid; read -r pw
    if [ -n "$pw" ]; then sudo nmcli dev wifi connect "$ssid" password "$pw"; else sudo nmcli dev wifi connect "$ssid"; fi
    sleep 3; echo "robot addresses:"; ip -br -4 addr | grep -v "^lo"'
echo "Saved on the robot: it joins \"$ssid\" at every boot. On that network: ssh radxa@$ROBOT"
