#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Copy a robot's SD card into an image to flash other robots (docs/sd_image.md); Linux PC, needs sudo.
# Run systemd/prepare-image.sh on the robot first (it powers it off), then put its card in this PC's reader:
#
#   tools/make_image.sh /dev/sdX microban.img      # -> microban.img.xz, shrunk to its data
#
# Needs parted, e2fsprogs and xz (Ubuntu: installed). The image keeps the card's partitions; the last one (the root filesystem) is shrunk to its data plus a margin,
# and grows back to the whole card at the copy's first boot (microban-firstboot).
set -euo pipefail
DEV=${1:-}; OUT=${2:-microban.img}
[ -b "$DEV" ] || [ -f "$DEV" ] || { echo "usage: tools/make_image.sh /dev/sdX out.img   (the card: lsblk)"; exit 1; }
MARGIN_MB=300                                  # free space left in the image's root filesystem

lsblk -o NAME,SIZE,TYPE,TRAN,RM,MODEL,MOUNTPOINT "$DEV" 2>/dev/null || ls -lh "$DEV"
if lsblk -n -o MOUNTPOINT "$DEV" 2>/dev/null | grep -qE '^/(boot.*)?$'; then echo "$DEV holds this PC's system: refusing"; exit 1; fi
read -r -p "Copy ALL of $DEV into $OUT? (type yes) " ok
[ "$ok" = yes ] || exit 1
for p in $(lsblk -n -o NAME -l "$DEV" 2>/dev/null | tail -n +2); do sudo umount "/dev/$p" 2>/dev/null || true; done

echo "1/4 copy of the card"
sudo dd if="$DEV" of="$OUT" bs=4M status=progress conv=fsync
sudo chown "$(id -u):$(id -g)" "$OUT"

echo "2/4 shrink of the root filesystem"
LOOP=$(sudo losetup --show -fP "$OUT")
trap 'sudo losetup -d "$LOOP" 2>/dev/null || true' EXIT
PART=$(lsblk -n -o NAME -l "$LOOP" | tail -1)          # the last partition: the root filesystem
NUM=${PART##*p}
sudo e2fsck -fy "/dev/$PART" >/dev/null || true
sudo resize2fs -M "/dev/$PART"
BS=$(sudo dumpe2fs -h "/dev/$PART" 2>/dev/null | awk -F: '/^Block size/ {print $2+0}')
BLOCKS=$(sudo dumpe2fs -h "/dev/$PART" 2>/dev/null | awk -F: '/^Block count/ {print $2+0}')
BLOCKS=$((BLOCKS + MARGIN_MB * 1024 * 1024 / BS))
sudo resize2fs "/dev/$PART" "$BLOCKS"
SECTORS=$((BLOCKS * BS / 512))

echo "3/4 partition table"
START=$(sudo parted -s -m "$LOOP" unit s print | awk -F: -v n="$NUM" '$1 == n {sub("s", "", $2); print $2}')
sudo losetup -d "$LOOP"; trap - EXIT
printf "Yes\n" | sudo LC_ALL=C parted ---pretend-input-tty "$OUT" unit s resizepart "$NUM" "$((START + SECTORS - 1))" >/dev/null   # shrinking asks to confirm
truncate -s $(( (START + SECTORS + 34) * 512 + 1024 * 1024 )) "$OUT"   # + the backup GPT and 1 MiB
python3 - "$OUT" <<'PY'                                               # backup GPT moved to the new end
import os, struct, sys, zlib
f = open(sys.argv[1], "r+b"); n = os.path.getsize(sys.argv[1]) // 512
f.seek(512); h = bytearray(f.read(92))
hsize, entries_lba, count, esize = struct.unpack_from("<I", h, 12)[0], *struct.unpack_from("<QII", h, 72)
f.seek(entries_lba * 512); entries = f.read(count * esize)
def header(my, alt, ents):
    x = bytearray(h); struct.pack_into("<QQ", x, 24, my, alt); struct.pack_into("<Q", x, 48, n - 34)
    struct.pack_into("<Q", x, 72, ents); struct.pack_into("<I", x, 16, 0)
    struct.pack_into("<I", x, 16, zlib.crc32(bytes(x[:hsize])))
    return bytes(x)
f.seek(512); f.write(header(1, n - 1, entries_lba))
f.seek((n - 33) * 512); f.write(entries)
f.seek((n - 1) * 512); f.write(header(n - 1, 1, n - 33).ljust(512, b"\0"))
PY
sudo parted -s "$OUT" unit MiB print

echo "4/4 compression"
xz -T0 -6 -f -v "$OUT"
ls -lh "$OUT.xz"
echo "Flash it on a card (16 GB or more) with Raspberry Pi Imager or balenaEtcher (docs/sd_image.md)."
