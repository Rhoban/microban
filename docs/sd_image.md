# SD card image: flash a robot, reach it, add a wifi network

Every robot runs the same SD card: Debian 12 (Radxa), this repository in `~/microban` (branch `dev_v2`, its `.venv`
ready), and the robot service (the control loop starts at boot, torque off until a move is launched; see
[dashboard.md](dashboard.md)). User `radxa`, password `radxa` (sudo).

## Flash a robot

1. Flash `microban.img.xz` on a card of 16 GB or more (the image is 8.6 GB). Linux and macOS:
   `tools/flash_card.sh microban.img.xz`: it lists the removable cards first and asks which one (by number),
   refuses the PC's own disk and a card too small, asks to type the card's name again, writes, reads the card back
   to check it, and ejects it. Windows (or a graphical tool): [Raspberry Pi Imager](https://www.raspberrypi.com/software/)
   ("Use custom") or [balenaEtcher](https://etcher.balena.io/).
2. Put it in the robot and power it on. At its first boot (about 1 min) the robot grows its partition to the whole
   card and takes its own identity: machine-id, SSH keys, and the name `microban-XXXX`, XXXX being the end of its wifi
   MAC address. Two robots never share a name or a DHCP address. `make discover-robots` lists the robots on your
   network, with their name and address.
3. Tell it its version once: in the dashboard (`make dashboard`), the header's **robot version** menu, **Climber** for
   a robot with the climbing forearms and feet (a new robot is a Classic). The robot keeps it, and runs only the moves
   made for it ([moves.md](moves.md)).

## Reach it with an Ethernet cable

The image has no wifi network. Plug a cable straight between the robot and your PC: the robot always has a link-local
address (169.254.x.x) on it, besides DHCP, and announces itself on the cable (mDNS: `microban-XXXX.local`).
macOS and Windows do the same on their side by themselves. On a Linux PC with NetworkManager, give your Ethernet port a
link-local address once: `tools/robot_wifi.sh --direct <port>` (`ip -br link` lists the ports, e.g. `enp3s0`).

Then `ssh radxa@microban-XXXX.local`. To find XXXX: `avahi-browse -tr _ssh._tcp` (Linux, package `avahi-utils`),
`dns-sd -B _ssh._tcp` (macOS), or let `tools/robot_wifi.sh` look for it. A cable to a network with DHCP (a router)
works as well: the robot takes an address there.

## Add a wifi network

```bash
tools/robot_wifi.sh                       # finds the robot on the cable, lists the networks it sees, asks one
tools/robot_wifi.sh microban-1a2b.local   # the same for a given robot
tools/robot_wifi.sh --list                # the robot's saved networks and addresses
```

The robot keeps the network and joins it at every boot; then `ssh radxa@microban-XXXX.local` from a PC on that wifi.
To remove one: `ssh -t radxa@microban-XXXX.local sudo nmcli con delete <name>`. Your SSH key avoids typing the password:
`ssh-copy-id radxa@microban-XXXX.local`.

## Make the image (from a set-up robot)

1. On the robot, from `~/microban`: `sudo bash systemd/prepare-image.sh`. It installs the first-boot service, sets up
   the Ethernet port as above, removes the saved wifi networks and the authorized SSH keys (`--keep-wifi`,
   `--keep-ssh-keys` to keep them), clears logs, histories and caches, then powers the robot off. Keep the robot on
   the Ethernet cable to watch it: it loses its wifi.
2. Put its card in a Linux PC: `tools/make_image.sh /dev/sdX microban.img` (the card's device: `lsblk`). It copies
   the card, shrinks the root filesystem to its data (plus 300 MB) and compresses it: `microban.img.xz`.
3. That robot itself takes a new name (`microban-XXXX`) at its next boot, as every copy does.
