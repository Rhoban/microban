#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Flash the robot's SD card image (docs/sd_image.md) on a card, check it, eject it; Linux and macOS, needs sudo.
#
#   tools/flash_card.sh                              # asks the card first (numbered list), then the image
#   tools/flash_card.sh microban.img.xz              # the same with this image
#   tools/flash_card.sh microban.img.xz /dev/sdX     # no question (Linux /dev/sdX or /dev/mmcblkN, macOS /dev/diskN)
#
# Without an image given, it takes the microban*.img.xz of the current folder (or asks). Refuses the disk the PC runs on and a card smaller than the image; asks to type the card's name before writing.
# A progress bar shows the percent, GB done, MB/s and time left while it writes, then while it reads the card back
# to compare it with the image (--no-verify to skip; the bar needs python3).
# Windows: use Raspberry Pi Imager ("Use custom") or balenaEtcher.
set -euo pipefail

IMG=""; DEV=""; VERIFY=1
for a in "$@"; do
    case "$a" in
        --no-verify) VERIFY=0 ;;
        -h|--help) sed -n '4,12p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        /dev/*) DEV=$a ;;
        *) IMG=$a ;;
    esac
done
OS=$(uname -s)

dev_size() {             # bytes
    if [ "$OS" = Darwin ]; then diskutil info "$1" | awk -F'[()]' '/Disk Size/ {print $2+0}'
    else lsblk -b -d -n -o SIZE "$1"; fi
}
card_names() {           # the removable disks: /dev/...
    if [ "$OS" = Darwin ]; then diskutil list external physical | awk '/^\/dev\/disk/ {print $1}'
    else lsblk -d -n -o NAME,TRAN,RM | awk '$3 == 1 || $2 == "usb" || $1 ~ /^mmcblk/ {print "/dev/"$1}'; fi
}
card_label() {
    if [ "$OS" = Darwin ]; then echo "$1  $(diskutil info "$1" | awk -F: '/Disk Size/ {print $2}' | cut -d'(' -f1 | xargs)  $(diskutil info "$1" | awk -F: '/Media Name/ {print $2}' | xargs)"
    else lsblk -d -n -o NAME,SIZE,TRAN,MODEL "$1" | awk '{printf "/dev/%s  %s  %s  %s %s %s", $1, $2, $3, $4, $5, $6}'; fi
}
system_disk() {          # the disk the PC runs on
    if [ "$OS" = Darwin ]; then diskutil info / | awk '/Part of Whole/ {print "/dev/"$4}'
    else echo "/dev/$(lsblk -n -o PKNAME "$(findmnt -n -o SOURCE /)" | head -1)"; fi
}

# 1. the card, before anything else
if [ -z "$DEV" ]; then
    cards=(); while read -r c; do cards+=("$c"); done < <(card_names)        # (macOS bash 3.2: no mapfile)
    [ ${#cards[@]} -gt 0 ] || { echo "No removable card found: insert the card (or give it: tools/flash_card.sh IMAGE /dev/sdX)"; exit 1; }
    echo "Card to flash:"
    for i in "${!cards[@]}"; do printf "  %d) %s\n" $((i + 1)) "$(card_label "${cards[$i]}")"; done
    read -r -p "Number: " k
    [[ "$k" =~ ^[0-9]+$ ]] && [ "$k" -ge 1 ] && [ "$k" -le ${#cards[@]} ] || { echo "cancelled"; exit 1; }
    DEV=${cards[$((k - 1))]}
fi
[ -b "$DEV" ] || [ -f "$DEV" ] || { echo "$DEV is not a disk"; exit 1; }

# 2. the image
if [ -z "$IMG" ]; then
    IMG=$(ls -t microban*.img.xz 2>/dev/null | head -1 || true)
    [ -n "$IMG" ] || read -r -p "Image to flash (.img.xz): " IMG
fi
[ -f "$IMG" ] || { echo "no image $IMG"; exit 1; }
# the image's size and how to read it
case "$IMG" in
    *.xz) SIZE=$(xz --robot --list "$IMG" | awk '$1 == "totals" {print $5}'); READ=(xz -dc "$IMG") ;;
    *.zst) SIZE=$(zstd -lv "$IMG" 2>/dev/null | awk '/Decompressed Size/ {gsub(/[(),]/, "", $5); print $5}'); READ=(zstd -dc "$IMG") ;;
    *) SIZE=$(wc -c < "$IMG" | tr -d ' '); READ=(cat "$IMG") ;;
esac
[ -n "$SIZE" ] || { echo "cannot read the size of $IMG"; exit 1; }
echo "Image: $IMG ($((SIZE / 1000000)) MB once written)"

if [ -b "$DEV" ]; then
    [ "$DEV" = "$(system_disk)" ] && { echo "$DEV is the disk this PC runs on: refusing"; exit 1; }
    if [ "$OS" != Darwin ] && lsblk -n -o MOUNTPOINT "$DEV" 2>/dev/null | grep -qE '^(/|/boot.*|/home|/usr|/var|\[SWAP\])$'; then
        echo "$DEV holds a system folder of this PC (mounted): refusing"; exit 1
    fi
    CARD=$(dev_size "$DEV")
    [ "$CARD" -ge "$SIZE" ] || { echo "$DEV holds $((CARD / 1000000)) MB, the image needs $((SIZE / 1000000)) MB: take a 16 GB card"; exit 1; }
    echo "Card: $DEV, $((CARD / 1000000)) MB"
fi
read -r -p "Everything on $DEV will be erased. Type its name again to go on ($DEV): " ok
[ "$ok" = "$DEV" ] || { echo "cancelled"; exit 1; }

# unmount, write (macOS: the raw device /dev/rdiskN is much faster)
OUTDEV=$DEV
if [ "$OS" = Darwin ] && [ -b "$DEV" ]; then
    diskutil unmountDisk "$DEV" >/dev/null; OUTDEV=${DEV/\/dev\/disk//dev/rdisk}
elif [ -b "$DEV" ]; then
    for p in $(lsblk -n -l -o NAME "$DEV" | tail -n +2); do sudo umount "/dev/$p" 2>/dev/null || true; done
fi
# progress bar on a stream: percent, GB done / total, MB/s, time left (python3; without it, no bar)
progress() {             # progress LABEL BYTES: copies stdin to stdout
    if ! command -v python3 >/dev/null; then cat; return; fi
    python3 -c '
import sys, time
label, total = sys.argv[1], int(sys.argv[2])
inp, out = sys.stdin.buffer, sys.stdout.buffer
done, t0, last = 0, time.time(), 0.0
def show(end=False):
    dt = max(time.time() - t0, 1e-6); rate = done / dt; frac = min(done / total, 1.0) if total else 1.0
    left = (total - done) / rate if rate > 0 else 0
    bar = "#" * int(30 * frac) + "-" * (30 - int(30 * frac))
    sys.stderr.write("\r%s [%s] %3d%%  %.2f / %.2f GB  %5.1f MB/s  %s   " % (label, bar, 100 * frac, done / 1e9,
                     total / 1e9, rate / 1e6, "done in %d:%02d" % divmod(int(dt), 60) if end else
                     "%d:%02d left" % divmod(int(left), 60)))
    sys.stderr.flush()
while True:
    b = inp.read(4 << 20)
    if not b: break
    out.write(b); done += len(b)
    if time.time() - last > 0.5: show(); last = time.time()
out.flush(); show(True); sys.stderr.write("\n")
' "$1" "$2"
}

# the card writes without the page cache (Linux O_DIRECT, macOS raw device): the bar shows the card's real speed
if [ "$OS" = Darwin ]; then DD=(sudo dd of="$OUTDEV" bs=4m); else DD=(sudo dd of="$OUTDEV" bs=4M iflag=fullblock oflag=direct); fi
[ -f "$OUTDEV" ] && DD=(sudo dd of="$OUTDEV" bs=4M conv=notrunc)            # a file (tests): no O_DIRECT
"${READ[@]}" | progress "Writing " "$SIZE" | "${DD[@]}" 2>/dev/null
sync

if [ "$VERIFY" = 1 ]; then
    # the image's checksum in the background while the card is read back
    sumfile=$(mktemp); ("${READ[@]}" | shasum -a 256 | cut -d' ' -f1 > "$sumfile") &
    got=$(sudo head -c "$SIZE" "$OUTDEV" | progress "Checking" "$SIZE" | shasum -a 256 | cut -d' ' -f1)
    wait; want=$(cat "$sumfile"); rm -f "$sumfile"
    if [ "$want" != "$got" ]; then echo "CHECK FAILED: the card differs from the image (bad card or reader?)"; exit 1; fi
    echo "Check OK: the card is identical to the image"
fi

if [ -b "$DEV" ]; then
    if [ "$OS" = Darwin ]; then diskutil eject "$DEV" >/dev/null; else sudo eject "$DEV" 2>/dev/null || true; fi
fi
echo "Done: put the card in the robot. First boot ~1 min, then ssh radxa@microban-XXXX.local (docs/sd_image.md)."
