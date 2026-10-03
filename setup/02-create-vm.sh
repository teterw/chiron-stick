#!/bin/bash
# Phase 1: create the build VM: UEFI with Secure Boot (Microsoft keys enrolled), the Mint ISO,
# and the whole target SSD passed through by its by-id path.
# Usage: setup/02-create-vm.sh [--dry-run] </dev/disk/by-id/usb-...> <target-drive-serial>
#   Optional: VM_NAME (chiron-build), VM_MEMORY_MB (4096), VM_VCPUS (4)
set -euo pipefail
. "$(dirname "$0")/lib/common.sh"
parse_args "$@"

DEV=${ARGS[0]:-}
SERIAL=${ARGS[1]:-}
[ -n "$DEV" ] && [ -n "$SERIAL" ] || die "usage: $0 [--dry-run] /dev/disk/by-id/usb-... <target-drive-serial>"
VM=${VM_NAME:-chiron-build}
ISO=/var/lib/libvirt/boot/chiron/linuxmint-22.3-xfce-64bit.iso
V="virsh -c qemu:///system"

[ -r "$ISO" ] || die "ISO not found: run setup/01-get-mint-iso.sh first"
check_target "$DEV" "$SERIAL"
$V dominfo "$VM" >/dev/null 2>&1 && die "VM '$VM' already exists"

# Never two running VMs on the target disk (CLAUDE.md safety rule 4)
REAL=$(readlink -f "$DEV")
for d in $($V list --name); do
  if $V domblklist "$d" --details | grep -qE "(^|[[:space:]])($DEV|$REAL)([[:space:]]|$)"; then
    die "running VM '$d' already uses the target disk"
  fi
done

run virt-install --connect qemu:///system --name "$VM" --osinfo ubuntu24.04 \
  --memory "${VM_MEMORY_MB:-4096}" --vcpus "${VM_VCPUS:-4}" --machine q35 \
  --boot firmware=efi,firmware.feature0.name=secure-boot,firmware.feature0.enabled=yes,firmware.feature1.name=enrolled-keys,firmware.feature1.enabled=yes \
  --disk "path=$DEV,bus=sata,cache=none,io=native,discard=unmap" \
  --cdrom "$ISO" \
  --network network=default,model=virtio \
  --graphics spice \
  --noautoconsole

[ "$DRY_RUN" = 1 ] && exit 0
echo "== Check: Secure Boot firmware and disk source =="
$V dumpxml "$VM" | grep -E "<loader|<nvram|firmware=|feature (enabled|name)|<source dev=|<source file="
echo "VM '$VM' started. Open it with: virt-manager (or: virt-viewer -c qemu:///system $VM)"
