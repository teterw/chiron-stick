#!/bin/bash
# Phase 1: prepare a Fedora host to build Chiron Stick inside a VM.
# Usage: sudo setup/00-host-prep.sh [--dry-run] <target-drive-serial>
#   Find the serial with: lsblk -o NAME,SIZE,MODEL,SERIAL,TRAN
set -euo pipefail
. "$(dirname "$0")/lib/common.sh"
parse_args "$@"

SERIAL=${ARGS[0]:-}
[ -n "$SERIAL" ] || die "usage: $0 [--dry-run] <target-drive-serial>"
[ "$(id -u)" = 0 ] || [ "$DRY_RUN" = 1 ] || die "run as root (sudo or pkexec)"
OWNER=${SUDO_USER:-}
[ -z "$OWNER" ] && [ -n "${PKEXEC_UID:-}" ] && OWNER=$(id -nu "$PKEXEC_UID")
[ -n "$OWNER" ] || OWNER=$(id -nu)
[ "$OWNER" != root ] || [ "$DRY_RUN" = 1 ] || die "can't tell which user should get VM access; run it with sudo or pkexec"

echo "== Virtualization tools =="
run dnf install -y qemu-kvm libvirt-daemon-kvm libvirt-daemon-config-network edk2-ovmf \
  virt-install virt-manager virt-viewer python3-virt-firmware

echo "== VM access for $OWNER (libvirt group) =="
run usermod -aG libvirt "$OWNER"

echo "== ISO folder the VM can read =="
run install -d -o "$OWNER" -g "$OWNER" -m 0755 /var/lib/libvirt/boot/chiron

echo "== Never automount the target SSD on this host (CLAUDE.md safety rule 4) =="
RULE="ENV{ID_SERIAL_SHORT}==\"$SERIAL\", ENV{UDISKS_AUTO}=\"0\", ENV{UDISKS_IGNORE}=\"1\""
if [ "$DRY_RUN" = 1 ]; then
  echo "[dry-run] write /etc/udev/rules.d/99-chiron-target.rules: $RULE"
else
  printf '# Chiron Stick target SSD: never automount or show it on this host.\n# Partitions inherit ID_SERIAL_SHORT from the disk.\n%s\n' "$RULE" \
    > /etc/udev/rules.d/99-chiron-target.rules
fi
run udevadm control --reload
run udevadm trigger --action=change --subsystem-match=block --property-match=ID_SERIAL_SHORT="$SERIAL"

echo "== libvirt daemons and the NAT network 'default' =="
run systemctl enable --now virtqemud.socket virtnetworkd.socket virtstoraged.socket
run virsh -c qemu:///system net-autostart default
if ! virsh -c qemu:///system net-info default 2>/dev/null | grep -q 'Active:.*yes'; then
  run virsh -c qemu:///system net-start default
fi

echo "Host ready. Log out and back in (or use 'sg libvirt') so the libvirt group applies."
