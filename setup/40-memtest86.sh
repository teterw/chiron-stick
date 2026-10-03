#!/bin/bash
# Phase 6: PassMark MemTest86 Free in the stick's boot menu (UEFI). Run it ON the stick, as root.
# Usage: sudo setup/40-memtest86.sh [--dry-run]
#
# Never commit MemTest86's files: its licence grants no right to pass the software on, so every
# builder downloads their own copy here. No checksum is published, so instead the program's
# Authenticode signature is verified against Microsoft's UEFI CA 2011 certificate, the same
# check the firmware does under Secure Boot.
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
. "$HERE/lib/common.sh"
parse_args "$@"
[ "$(id -u)" = 0 ] || [ "$DRY_RUN" = 1 ] || die "run as root on the stick"
mountpoint -q /boot/efi || die "/boot/efi isn't mounted"

ZIP_URL=https://www.memtest86.com/downloads/memtest86-usb.zip
MS_CA_URL=https://www.microsoft.com/pkiops/certs/MicCorUEFCA2011_2011-06-27.crt
DEST=/boot/efi/EFI/memtest86
GRUB_SCRIPT=/etc/grub.d/42_chiron_memtest86
UA="Mozilla/5.0 (X11; Linux x86_64) chiron-stick-setup"

if [ "$DRY_RUN" = 1 ]; then
  echo "[dry-run] download $ZIP_URL, verify BOOTX64.efi against Microsoft's UEFI CA 2011, copy to $DEST,"
  echo "[dry-run] write $GRUB_SCRIPT (UEFI only), show the GRUB menu for 5 s, update-grub"
  exit 0
fi
command -v sbverify >/dev/null || apt-get install -y -q sbsigntool
command -v unzip >/dev/null || apt-get install -y -q unzip

W=$(mktemp -d)
LOOP=""
cleanup() {
  mountpoint -q "$W/mnt" 2>/dev/null && umount "$W/mnt"
  [ -n "$LOOP" ] && losetup -d "$LOOP"
  rm -rf "$W"
}
trap cleanup EXIT

echo "===== 1. Download"
curl -fsSL -A "$UA" -e https://www.memtest86.com/download.htm -o "$W/mt86.zip" "$ZIP_URL"
unzip -q -o "$W/mt86.zip" memtest86-usb.img -d "$W"

echo "===== 2. Take the files from the image's EFI partition (read-only loop mount)"
LOOP=$(losetup -r -P -f --show "$W/memtest86-usb.img")
udevadm settle || true
mkdir -p "$W/mnt"
esp=""
for p in "$LOOP"p*; do  # probe directly: udev may not have filled in partition types yet
  if [ "$(blkid -p -o value -s PART_ENTRY_TYPE "$p" 2>/dev/null | tr 'A-Z' 'a-z')" = c12a7328-f81f-11d2-ba4b-00a0c93ec93b ]; then
    esp=$p; break
  fi
done
[ -n "$esp" ] || die "no EFI partition in the MemTest86 image"
mount -o ro "$esp" "$W/mnt"
mkdir -p "$W/files"
cp "$W/mnt/EFI/BOOT/BOOTX64.efi" "$W/mnt/EFI/BOOT/unifont.bin" "$W/mnt/EFI/BOOT/blacklist.cfg" "$W/mnt/EFI/BOOT/mt86.png" \
   "$W/mnt/license.rtf" "$W/files/"
version=$(strings "$W/files/BOOTX64.efi" | grep -m1 -oE 'MemTest86 V[0-9.]+( Build: [0-9]+)?' || echo "MemTest86")

echo "===== 3. Verify the signature (Microsoft Corporation UEFI CA 2011)"
curl -fsSL -o "$W/ms-uefi-ca-2011.crt" "$MS_CA_URL"
openssl x509 -inform DER -in "$W/ms-uefi-ca-2011.crt" -out "$W/ms-uefi-ca-2011.pem"
openssl x509 -in "$W/ms-uefi-ca-2011.pem" -noout -subject | grep -q 'Microsoft Corporation UEFI CA 2011' || die "unexpected certificate from $MS_CA_URL"
sbverify --cert "$W/ms-uefi-ca-2011.pem" "$W/files/BOOTX64.efi" || die "MemTest86's signature does NOT verify: not installing it"

echo "===== 4. Install to $DEST"
mkdir -p "$DEST"
cp "$W/files/"* "$DEST/"
sha=$(sha256sum "$DEST/BOOTX64.efi" | cut -d' ' -f1)
echo "$version, BOOTX64.efi sha256 $sha, installed $(date -u +%F)" > "$DEST/VERSION.txt"
cat "$DEST/VERSION.txt"

echo "===== 5. GRUB menu entry (UEFI only: MemTest86 v11 has no legacy-BIOS build)"
cat > "$GRUB_SCRIPT" <<'EOF'
#!/bin/sh
# Chiron Stick: MemTest86 (setup/40-memtest86.sh)
exec tail -n +4 "$0"
if [ "$grub_platform" = "efi" ]; then
  menuentry "MemTest86 (RAM test)" --class memtest {
    insmod part_gpt
    insmod fat
    insmod chain
    search --no-floppy --set=root --file /EFI/memtest86/BOOTX64.efi
    chainloader /EFI/memtest86/BOOTX64.efi
  }
fi
EOF
chmod 0755 "$GRUB_SCRIPT"
grep -q '^GRUB_TIMEOUT_STYLE=menu' /etc/default/grub.d/99-chiron.cfg 2>/dev/null ||
  echo "NOTE: the boot menu is hidden; rerun setup/10-base-config.sh (its 99-chiron.cfg shows it for 5 s)"
update-grub
grep -q 'MemTest86 (RAM test)' /boot/grub/grub.cfg && echo "GRUB entry: OK"
echo "Phase 6 done. Test it: reboot and pick 'MemTest86 (RAM test)' in the boot menu."
