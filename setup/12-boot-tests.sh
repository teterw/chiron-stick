#!/bin/bash
# Phase 3 boot tests: does the stick boot on firmware that has never seen it?
#   1. UEFI + Secure Boot (Microsoft keys) with fresh firmware variables, so no boot entries:
#      it must boot through the removable path EFI/BOOT/BOOTX64.EFI
#   2. Legacy BIOS (SeaBIOS): it must boot GRUB from the BIOS boot partition
# Each test VM runs alone on the target disk (CLAUDE.md safety rule 4), is screenshotted once it
# should have reached the disk unlock prompt, then removed (including its firmware variables).
# Usage: setup/12-boot-tests.sh [--dry-run] </dev/disk/by-id/usb-...> <drive-serial> [screenshot-dir]
#   Optional: BOOT_WAIT seconds before the screenshot (default 45)
set -eu
. "$(dirname "$0")/lib/common.sh"
parse_args "$@"

DEV=${ARGS[0]:-}
SERIAL=${ARGS[1]:-}
OUT=${ARGS[2]:-.}
[ -n "$DEV" ] && [ -n "$SERIAL" ] || die "usage: $0 [--dry-run] /dev/disk/by-id/usb-... <drive-serial> [screenshot-dir]"
V="virsh -c qemu:///system"
REAL=$(readlink -f "$DEV")

check_target "$DEV" "$SERIAL"
for d in $($V list --name); do
  if $V domblklist "$d" --details | grep -qE "(^|[[:space:]])($DEV|$REAL)([[:space:]]|$)"; then
    die "VM '$d' is running on the target disk: shut it down first"
  fi
done
mkdir -p "$OUT"

# boot_test <name> <virt-install --boot value>
boot_test() {
  local name=$1 boot=$2
  echo "== $name"
  if $V dominfo "$name" >/dev/null 2>&1; then die "a VM named $name already exists"; fi
  run virt-install --connect qemu:///system --name "$name" --osinfo ubuntu24.04 \
    --memory 2048 --vcpus 2 --machine q35 --boot "$boot" \
    --disk "path=$DEV,bus=sata,cache=none,io=native" \
    --network none --graphics spice --import --noautoconsole \
    --check path_in_use=off  # the build VM's definition uses this disk too; we checked nothing is *running* on it
  [ "$DRY_RUN" = 1 ] && { echo "[dry-run] wait ${BOOT_WAIT:-45}s, screenshot to $OUT/$name.png, remove $name"; return; }
  sleep "${BOOT_WAIT:-45}"
  $V screenshot "$name" "$OUT/$name.png" >/dev/null
  echo "screenshot: $OUT/$name.png (expect the disk unlock prompt)"
  $V destroy "$name" >/dev/null
  $V undefine "$name" --nvram >/dev/null 2>&1 || $V undefine "$name" >/dev/null
}

boot_test chiron-test-uefi-fresh hd,firmware=efi,firmware.feature0.name=secure-boot,firmware.feature0.enabled=yes,firmware.feature1.name=enrolled-keys,firmware.feature1.enabled=yes
boot_test chiron-test-bios hd
echo "Done. Check both screenshots, then start the build VM again."
