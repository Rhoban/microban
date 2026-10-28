#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
#
# First boot of a robot flashed from a Microban SD card image (systemd/prepare-image.sh made it): the root partition
# grows to the whole card, and the robot gets its own identity, so that several robots can share a network:
# a new machine-id (DHCP addresses depend on it), new SSH host keys, and the hostname microban-XXXX (XXXX: the end of
# its wifi MAC address: `ssh radxa@microban-XXXX.local`, see docs/sd_image.md).
# Run once by microban-firstboot.service, before the network starts, while /etc/microban-firstboot exists.
set -uo pipefail

log() { echo "microban-firstboot: $*"; }

# 1. root partition and filesystem to the whole card (the image is shrunk to its data)
root_dev=$(findmnt -n -o SOURCE /)                       # /dev/mmcblk1p3
disk=/dev/$(lsblk -n -o PKNAME "$root_dev")
part=$(cat "/sys/class/block/$(basename "$root_dev")/partition")
growpart "$disk" "$part" && log "partition $root_dev grown" || log "partition $root_dev already full"
resize2fs "$root_dev" && log "filesystem $root_dev resized"

# 2. a new machine-id
rm -f /etc/machine-id /var/lib/dbus/machine-id
systemd-machine-id-setup
[ -d /var/lib/dbus ] && ln -sf /etc/machine-id /var/lib/dbus/machine-id
log "machine-id $(cat /etc/machine-id)"

# 3. new SSH host keys
rm -f /etc/ssh/ssh_host_*
ssh-keygen -A
log "SSH host keys regenerated"

# 4. hostname microban-XXXX from the wifi MAC address (the Ethernet one may be random at each boot)
for _ in $(seq 30); do compgen -G "/sys/class/net/wl*" >/dev/null && break; sleep 1; done   # its driver loads late
mac=""
for i in /sys/class/net/wl*/address /sys/class/net/en*/address; do
    [ -e "$i" ] && mac=$(tr -d ':' < "$i") && break
done
[ -n "$mac" ] || mac=$(cat /etc/machine-id)            # no network interface found: the new machine-id
name="microban-${mac: -4}"
hostnamectl set-hostname "$name"
cat > /etc/hosts <<EOF
127.0.0.1 localhost
127.0.1.1 $name
EOF
log "hostname $name"

rm -f /etc/microban-firstboot
log "done"
