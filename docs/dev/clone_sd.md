# Cloning the SD card

This produces the distributable `microban.img.xz`. Do the **one-time setup** once on
the master card, then the **depersonalization** and **imaging** steps every time you
cut a new image.

## One-time setup: SSH host-key regeneration

A distributed image must not ship with fixed SSH host keys — otherwise every robot
flashed from it shares the same keys (a security risk, and SSH host-key conflicts when
two robots run on the same network). We remove the keys before imaging (see below) and
let each robot regenerate its own on first boot.

Raspberry Pi OS already ships `sshd-keygen.service`, but it only runs when
`ConditionFirstBoot=yes` (i.e. `/etc/machine-id` is empty). Add a more robust service,
triggered by the **absence of host keys**, so they always regenerate when missing.

On the Pi (`ssh microban`):
```bash
sudo tee /etc/systemd/system/regen-ssh-host-keys.service >/dev/null <<'EOF'
[Unit]
Description=Regenerate SSH host keys if missing
Before=ssh.service ssh.socket sshd.service
ConditionPathExists=!/etc/ssh/ssh_host_ed25519_key

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/bin/ssh-keygen -A

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable regen-ssh-host-keys.service
```

## Depersonalize before each clone

Right before imaging, remove everything personal/unique so each user gets a clean,
private robot. Power off the Pi, insert the SD into your PC, then (adjust the mount
paths if needed):

```bash
R=/media/$USER/rootfs

# SSH host keys — regenerated on first boot by regen-ssh-host-keys.service
sudo rm -f "$R"/etc/ssh/ssh_host_*

# machine-id — regenerated on first boot; ensures unique DHCP identity / IP per robot
sudo truncate -s 0 "$R/etc/machine-id"

# Your Wi-Fi credentials (if any NetworkManager connection was created)
sudo rm -f "$R"/etc/NetworkManager/system-connections/*.nmconnection

# Your SSH public key, shell history, caches and logs
sudo rm -f "$R/home/user/.ssh/authorized_keys"
sudo rm -f "$R/home/user/.bash_history"
sudo rm -f "$R"/var/cache/apt/archives/*.deb
sudo rm -rf "$R"/var/log/journal/* "$R"/var/log/*.log "$R"/var/log/*.gz
```

Reset the Wi-Fi config to placeholders so it does not ship with your network
credentials:
```bash
sudo tee /media/$USER/bootfs/network-config >/dev/null <<'EOF'
network:
  version: 2
  ethernets:
    eth0:
      dhcp4: true
      dhcp6: true
      optional: true
  wifis:
    wlan0:
      dhcp4: true
      regulatory-domain: "<YOUR_COUNTRY_CODE>"
      access-points:
        "<YOUR_WIFI_NAME>":
          password: "<YOUR_WIFI_PASSWORD>"
      optional: true
EOF
```

Also confirm the password is the documented default (`user` / `password`) and the
hostname is `microban`, so the image matches [the deployment guide](../deployment.md).

## Create and shrink the image

Go to gnome disks and create an image of the SD card.

Then shrink and compress it. The `-Z` flag compresses the shrunk image with `xz`
(turning a ~4 GB raw image into a few hundred MB), and `-a` runs the compression in
parallel across all CPU cores — much faster than the default single-threaded `xz`:
```
wget https://raw.githubusercontent.com/Drewsif/PiShrink/master/pishrink.sh
chmod +x pishrink.sh
sudo ./pishrink.sh -aZ ~/Documents/microban.img
```

This produces `~/Documents/microban.img.xz`. Check the final size with:
```
ls -lh ~/Documents/microban.img.xz
```
