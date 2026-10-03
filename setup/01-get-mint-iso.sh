#!/bin/bash
# Phase 1: download the Linux Mint 22.3 Xfce ISO and verify it (GPG signature, then SHA256).
# Usage: setup/01-get-mint-iso.sh [--dry-run] [mirror-base-url]
#   Mirrors: https://www.linuxmint.com/mirrors.php (default: kernel.org). Any mirror is fine:
#   the checksum list is signed by Linux Mint.
set -euo pipefail
. "$(dirname "$0")/lib/common.sh"
parse_args "$@"

MIRROR=${ARGS[0]:-https://mirrors.edge.kernel.org/linuxmint/}
MIRROR=${MIRROR%/}
REL=22.3
ISO=linuxmint-$REL-xfce-64bit.iso
DIR=/var/lib/libvirt/boot/chiron
FPR=27DEB15644C6B3CF3BD7D291300F846BA25BAE09   # Linux Mint ISO Signing Key (Mint's verification guide)

[ -d "$DIR" ] && [ -w "$DIR" ] || die "$DIR is missing or not writable: run setup/00-host-prep.sh first"
cd "$DIR"

echo "== Checksum list and its signature =="
run curl -fsSL -o sha256sum.txt "$MIRROR/stable/$REL/sha256sum.txt"
run curl -fsSL -o sha256sum.txt.gpg "$MIRROR/stable/$REL/sha256sum.txt.gpg"
[ "$DRY_RUN" = 1 ] && { echo "[dry-run] verify signature, download $ISO if needed, check SHA256"; exit 0; }

G=$(mktemp -d)
trap 'rm -rf "$G"' EXIT
gpg --homedir "$G" -q --keyserver hkp://keys.openpgp.org:80 --recv-key "$FPR" 2>/dev/null ||
  gpg --homedir "$G" -q --keyserver hkps://keyserver.ubuntu.com --recv-key "$FPR"
gpg --homedir "$G" --status-fd 1 --verify sha256sum.txt.gpg sha256sum.txt 2>/dev/null |
  grep -q "^\[GNUPG:\] VALIDSIG $FPR " || die "BAD SIGNATURE on sha256sum.txt: don't use these files"
echo "signature OK: signed by the Linux Mint ISO Signing Key ($FPR)"

check() { grep " \*$ISO\$" sha256sum.txt | sha256sum -c --quiet - 2>/dev/null; }
if [ -f "$ISO" ] && check; then
  echo "ISO already present and verified: $DIR/$ISO"
  exit 0
fi

echo "== Downloading $ISO =="
curl -fL -C - --retry 5 --retry-delay 5 -o "$ISO" "$MIRROR/stable/$REL/$ISO"
check || die "CHECKSUM MISMATCH: delete $DIR/$ISO and download again"
echo "ISO verified: $DIR/$ISO"
