#!/bin/bash
# Phase 4: the diagnostic toolkit. Run it ON the stick (or in the build VM), as root.
# Usage: sudo setup/20-toolkit.sh [--dry-run]
# Installs without "recommends" on purpose: smartmontools would otherwise pull in a mail server.
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
. "$HERE/lib/common.sh"
parse_args "$@"
[ "$(id -u)" = 0 ] || [ "$DRY_RUN" = 1 ] || die "run as root on the stick"

export DEBIAN_FRONTEND=noninteractive
export HOME=${HOME:-/root}  # inxi complains without it (e.g. when run as a systemd job)
APT=(apt-get -y -q --no-install-recommends -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold)

PKGS=(
  # Inventory
  inxi lshw hwinfo dmidecode pciutils usbutils i2c-tools edid-decode
  # Storage
  smartmontools nvme-cli hdparm fio gsmartcontrol
  # CPU, thermal, load (turbostat and cpupower come with linux-tools for the HWE kernel)
  lm-sensors stress-ng s-tui htop btop sysstat linux-tools-generic-hwe-24.04
  # RAM
  memtester
  # GPU (Ubuntu 24.04 has no plain "glmark2" package: the X11 build is glmark2-x11)
  mesa-utils vulkan-tools glmark2-x11 nvtop intel-gpu-tools radeontop
  # Battery and power (no TLP or anything else that changes power settings)
  upower acpi powertop
  # Network
  iperf3 ethtool iw
  # Rescue and inspection
  gparted testdisk gddrescue ntfs-3g dislocker exfatprogs dosfstools btrfs-progs cryptsetup
  # Firmware: read-only use only (fwupdmgr get-devices / get-updates), never update an owner's firmware
  fwupd
)

echo "===== 1. Packages (${#PKGS[@]})"
if [ "$DRY_RUN" = 1 ]; then
  echo "[dry-run] debconf: iperf3 daemon off, sysstat collection off"
else
  debconf-set-selections <<'EOF'
iperf3 iperf3/start_daemon boolean false
sysstat sysstat/enable boolean false
EOF
fi
run apt-get update -q
run "${APT[@]}" install "${PKGS[@]}"

echo; echo "===== 2. No background daemons that touch the PC's disks"
# chiron reads SMART on demand; smartd would watch (and could change settings on) owner drives
if systemctl list-unit-files smartmontools.service >/dev/null 2>&1; then
  run systemctl disable --now smartmontools.service
  run systemctl mask smartmontools.service
fi
# No sensors-detect: it probes I2C/SMBus chips on the owner's board; auto-loaded drivers are enough

echo; echo "===== 3. Smoke test"
smoke() {  # smoke <label> <command...>: run it, show the first lines, report OK/FAILED
  echo "--- $1"
  if out=$("${@:2}" 2>&1); then printf '%s\n' "$out" | head -n "${SMOKE_LINES:-6}"; echo "OK"
  else printf '%s\n' "$out" | tail -n 3; echo "FAILED ($1)"; fi
}
if [ "$DRY_RUN" = 0 ]; then
  smoke "inxi -Fxz" inxi -Fxz -c0
  smoke "sensors (a VM may have none)" sh -c 'sensors || true'
  smoke "smartctl --scan" smartctl --scan
  smoke "upower -e" upower -e
  smoke "nvme list" nvme list
  smoke "fio" fio --version
  smoke "stress-ng" stress-ng --version
  smoke "turbostat" sh -c 'turbostat --version 2>&1 | head -n1'
  smoke "glmark2" glmark2 --version
  smoke "fwupd (read-only)" fwupdmgr --version
  smoke "smartd (expect: masked)" sh -c 'systemctl is-enabled smartmontools.service || true'
fi

echo; echo "===== 4. Snapshot toolkit"
if timeshift --list --scripted 2>/dev/null | grep -qw toolkit; then echo "snapshot 'toolkit' already exists"
else run timeshift --create --scripted --comments toolkit --tags O; fi
echo; echo "Phase 4 toolkit done."
