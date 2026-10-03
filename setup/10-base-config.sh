#!/bin/bash
# Phase 3: base configuration of the Chiron Stick. Run it ON the stick (or in the build VM), as root.
# Usage: sudo setup/10-base-config.sh [--dry-run]
#   PINNED_SHIM=/path/to/bootx64.efi  use this Microsoft-2011-signed shim if the installed one isn't
#                                     (EFI/boot/bootx64.efi from the verified Mint 22.3 ISO works)
# Safe to run again: every step checks first and only changes what isn't done yet.
# No pipefail: the "... | grep -q" checks would fail at random when grep exits early (SIGPIPE).
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
STICK=$(cd "$HERE/../stick" && pwd)
. "$HERE/lib/common.sh"
parse_args "$@"

[ "$(id -u)" = 0 ] || [ "$DRY_RUN" = 1 ] || die "run as root on the stick"
. /etc/os-release
[ "${UBUNTU_CODENAME:-$VERSION_CODENAME}" = noble ] || die "expected Linux Mint 22.x (Ubuntu 24.04 'noble' base)"
mountpoint -q /boot/efi || die "/boot/efi isn't mounted"
[ "$(findmnt -no FSTYPE /)" = btrfs ] || die "/ isn't btrfs"

export DEBIAN_FRONTEND=noninteractive
APT=(apt-get -y -q -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold)
ESP=/boot/efi
PIN=/usr/local/share/chiron/shim-2011

step() { echo; echo "===== $*"; }
installed() { dpkg-query -W -f='${Status}' "$1" 2>/dev/null | grep -q 'ok installed'; }
need_pkg() { installed "$1" || run "${APT[@]}" install "$1"; }

# put_file <path> <mode>: install stick/<path> to /<path> unless it's already identical
put_file() {
  if [ -f "/$1" ] && cmp -s "$STICK/$1" "/$1"; then echo "unchanged: /$1"; return; fi
  run install -D -m "$2" "$STICK/$1" "/$1"
  echo "installed: /$1"
}

# snapshot <name>: Timeshift on-demand snapshot, once
snapshot() {
  if timeshift --list --scripted 2>/dev/null | grep -qw -- "$1"; then echo "snapshot '$1' already exists"; return; fi
  run timeshift --create --scripted --comments "$1" --tags O
}

step "1. Pin the Microsoft-2011-signed shim (before any update can replace it)"
need_pkg sbsigntool
if [ -f "$PIN/shimx64.efi" ]; then
  echo "already pinned: $(cat "$PIN/VERSION" 2>/dev/null)"
else
  src=${PINNED_SHIM:-$ESP/EFI/ubuntu/shimx64.efi}
  sbverify --list "$src" | grep -q 'Microsoft Corporation UEFI CA 2011' ||
    die "$src isn't signed via the Microsoft Corporation UEFI CA 2011. Set PINNED_SHIM to EFI/boot/bootx64.efi from the verified Mint 22.3 ISO."
  run install -D -m 0644 "$src" "$PIN/shimx64.efi"
  if [ "$DRY_RUN" = 0 ]; then
    (cd "$PIN" && sha256sum shimx64.efi > shimx64.efi.sha256)
    echo "shim-signed $(dpkg-query -W -f='${Version}' shim-signed), pinned $(date -u +%F) from $src" > "$PIN/VERSION"
  fi
  echo "pinned: $src"
fi

step "2. GRUB never writes firmware boot entries; EFI/BOOT is kept by chiron-efi-sync"
if [ "$DRY_RUN" = 1 ]; then
  echo "[dry-run] debconf: grub2/update_nvram=false, grub2/no_efi_extra_removable=true, grub2/enable_os_prober=false, grub-pc/install_devices empty (accepted)"
else
  debconf-set-selections <<'EOF'
grub-pc grub2/update_nvram boolean false
grub-pc grub2/no_efi_extra_removable boolean true
grub-pc grub2/enable_os_prober boolean false
grub-pc grub-pc/install_devices multiselect
grub-pc grub-pc/install_devices_empty boolean true
EOF
fi
# The shim/GRUB package scripts call grub-install without --no-nvram, so wrap it (survives upgrades)
if dpkg-divert --list /usr/sbin/grub-install | grep -q 'grub-install.real'; then
  echo "grub-install is already diverted"
else
  run dpkg-divert --local --rename --divert /usr/sbin/grub-install.real --add /usr/sbin/grub-install
fi
put_file usr/local/lib/chiron/grub-install 0755
[ "$(readlink /usr/sbin/grub-install 2>/dev/null)" = /usr/local/lib/chiron/grub-install ] ||
  run ln -sfn /usr/local/lib/chiron/grub-install /usr/sbin/grub-install
put_file usr/local/sbin/chiron-efi-sync 0755
put_file usr/local/sbin/chiron-bios-grub 0755
put_file etc/apt/apt.conf.d/99-chiron-boot 0644
run /usr/local/sbin/chiron-efi-sync

step "3. Updates and the newest Ubuntu 24.04 HWE kernel"
run apt-get update -q
need_pkg linux-generic-hwe-24.04
run "${APT[@]}" full-upgrade
echo "running kernel: $(uname -r), newest installed: $(ls /boot/vmlinuz-* | sort -V | tail -n1 | sed 's|/boot/vmlinuz-||')"

step "4. Timeshift in btrfs mode (without @home, so 'chiron forget' really forgets), snapshot base-install"
if [ -f /etc/timeshift/timeshift.json ] && grep -q '"btrfs_mode" *: *"true"' /etc/timeshift/timeshift.json; then
  echo "Timeshift already configured"
else
  root_src=$(findmnt -no SOURCE --nofsroot /)
  btrfs_uuid=$(blkid -s UUID -o value "$root_src")
  # lsblk shows no parent for device-mapper volumes; the kernel's slaves/ link names the LUKS partition
  dm=$(basename "$(readlink -f "$root_src")")
  luks_uuid=$(blkid -s UUID -o value "/dev/$(ls "/sys/class/block/$dm/slaves" | head -n1)")
  if [ "$DRY_RUN" = 1 ]; then
    echo "[dry-run] write /etc/timeshift/timeshift.json: btrfs mode, device $btrfs_uuid (LUKS $luks_uuid), no schedules, no @home"
  else
    python3 - "$btrfs_uuid" "$luks_uuid" <<'PY'
import json, sys
cfg = json.load(open("/etc/timeshift/default.json"))
cfg.update({"backup_device_uuid": sys.argv[1], "parent_device_uuid": sys.argv[2], "do_first_run": "false",
            "btrfs_mode": "true", "include_btrfs_home": "false", "schedule_monthly": "false",
            "schedule_weekly": "false", "schedule_daily": "false", "schedule_hourly": "false", "schedule_boot": "false"})
json.dump(cfg, open("/etc/timeshift/timeshift.json", "w"), indent=2)
PY
    echo "configured: /etc/timeshift/timeshift.json"
  fi
fi
snapshot base-install

step "5. Generic initramfs (MODULES=most, so it boots on most hardware)"
grep -qE '^MODULES=most' /etc/initramfs-tools/initramfs.conf || die "initramfs.conf doesn't say MODULES=most"
if grep -rlsE '^[[:space:]]*MODULES=' /etc/initramfs-tools/conf.d/; then die "a conf.d file overrides MODULES"; fi
echo "MODULES=most, no overrides"

step "6. Legacy-BIOS GRUB on the stick's own disk"
need_pkg grub-pc-bin
run /usr/local/sbin/chiron-bios-grub --force

step "7. GRUB without os-prober, kernel without efi-pstore"
put_file etc/default/grub.d/99-chiron.cfg 0644
run update-grub

step "8. Never auto-start the PC's RAID arrays or LVM volumes"
initramfs_changed=0
if [ -f /etc/mdadm/mdadm.conf ]; then
  if grep -qE '^[[:space:]]*AUTO[[:space:]]+-all' /etc/mdadm/mdadm.conf; then
    echo "mdadm: AUTO -all already set"
  else
    run sh -c 'printf "\n# Chiron Stick: never auto-assemble RAID arrays found on the PC\nAUTO -all\n" >> /etc/mdadm/mdadm.conf'
    echo "mdadm: added AUTO -all"; initramfs_changed=1
  fi
fi
if command -v lvmconfig >/dev/null; then
  if lvmconfig activation/auto_activation_volume_list 2>/dev/null | grep -qE '=[[:space:]]*\[[[:space:]]*\]'; then
    echo "LVM: auto-activation already off"
  else
    run sh -c 'printf "\n# Chiron Stick: never auto-activate LVM volumes found on the PC\nactivation {\n\tauto_activation_volume_list = []\n}\n" >> /etc/lvm/lvmlocal.conf'
    if [ "$DRY_RUN" = 0 ]; then
      lvmconfig activation/auto_activation_volume_list | grep -qE '=[[:space:]]*\[[[:space:]]*\]' || die "LVM didn't pick up auto_activation_volume_list from lvmlocal.conf"
    fi
    echo "LVM: auto-activation off"; initramfs_changed=1
  fi
fi
[ "$initramfs_changed" = 1 ] && run update-initramfs -u -k all

step "9. Clock: chrony without rtcsync, never write the hardware clock (Windows keeps it in local time)"
need_pkg chrony
for f in /etc/chrony/chrony.conf /etc/chrony/conf.d/*.conf /etc/chrony/sources.d/*.sources; do
  [ -f "$f" ] || continue
  if grep -qE '^[[:space:]]*rtcsync' "$f"; then
    run sed -i -E 's/^([[:space:]]*)rtcsync/\1# rtcsync (Chiron Stick: never write the hardware clock)/' "$f"
    echo "disabled rtcsync in $f"; [ "$DRY_RUN" = 0 ] && systemctl restart chrony
  fi
done

step "10. No automounting of drives or media"
# Mint's defaults (mint-artwork, first in XDG_CONFIG_DIRS) turn automount on. Only per-user settings
# override them, so: new users get ours from /etc/skel, existing users get theirs set here.
SKEL_VOLMAN=etc/skel/.config/xfce4/xfconf/xfce-perchannel-xml/thunar-volman.xml
put_file "$SKEL_VOLMAN" 0644
for home in /home/*; do
  [ -d "$home" ] || continue
  u=$(stat -c %U "$home"); uid=$(id -u "$u" 2>/dev/null) || continue
  dir=$home/.config/xfce4/xfconf/xfce-perchannel-xml
  if [ -S "/run/user/$uid/bus" ]; then  # logged in: tell xfconfd, it saves the user's file
    for p in /automount-drives/enabled /automount-media/enabled; do
      run runuser -u "$u" -- env DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$uid/bus" \
        xfconf-query -c thunar-volman -p "$p" -n -t bool -s false
    done
    echo "automount off for $u (running session)"
  elif [ -f "$dir/thunar-volman.xml" ]; then
    run sed -i -E '/automount-(drives|media)/,/<\/property>/ s/(name="enabled" type="bool" value=)"true"/\1"false"/' "$dir/thunar-volman.xml"
    echo "automount off for $u (settings file)"
  else
    run runuser -u "$u" -- mkdir -p "$dir"
    run install -o "$u" -g "$(id -gn "$u")" -m 0644 "$STICK/$SKEL_VOLMAN" "$dir/thunar-volman.xml"
    echo "automount off for $u (new settings file)"
  fi
done

step "11. Swap: zram only (zstd, 50% of RAM), no swap on the USB drive"
need_pkg zram-tools
for kv in ALGO=zstd PERCENT=50 PRIORITY=100; do
  k=${kv%%=*}
  if grep -qE "^$k=" /etc/default/zramswap; then
    grep -qx "$kv" /etc/default/zramswap || run sed -i "s/^$k=.*/$kv/" /etc/default/zramswap
  else
    run sh -c "echo '$kv' >> /etc/default/zramswap"
  fi
done
[ "$DRY_RUN" = 0 ] && systemctl restart zramswap
if [ -e /swapfile ]; then die "/swapfile exists: remove it (and its fstab line) first"; fi
if grep -qE '^[^#].*[[:space:]]swap[[:space:]]' /etc/fstab; then die "/etc/fstab has a swap entry on the drive"; fi

step "12. Checks"
check() { printf '  %-30s %s\n' "$1" "$2"; }
check "Secure Boot" "$(mokutil --sb-state 2>&1 | head -n1)"
check "EFI/BOOT" "$(ls "$ESP/EFI/BOOT" | tr '\n' ' ')"
check "BOOTX64.EFI = pinned shim" "$(cmp -s "$PIN/shimx64.efi" "$ESP/EFI/BOOT/BOOTX64.EFI" && echo yes || echo NO)"
check "BOOTX64.EFI signed via" "$(sbverify --list "$ESP/EFI/BOOT/BOOTX64.EFI" 2>/dev/null | grep -m1 -o 'Microsoft Corporation UEFI CA 2011' || echo '?')"
check "grub-install" "$(dpkg-divert --list /usr/sbin/grub-install) -> $(readlink /usr/sbin/grub-install)"
check "debconf update_nvram" "$(debconf-show grub-pc | sed -n 's/.*grub2\/update_nvram: //p')"
check "os-prober disabled" "$(grep -c 'GRUB_DISABLE_OS_PROBER=true' /etc/default/grub.d/99-chiron.cfg) (99-chiron.cfg)"
check "pstore off in grub.cfg" "$(grep -q 'efi_pstore.pstore_disable=1' /boot/grub/grub.cfg && echo yes || echo NO)"
check "efi_pstore now" "$(cat /sys/module/efi_pstore/parameters/pstore_disable 2>/dev/null || echo 'not loaded') (Y after a reboot)"
check "BIOS GRUB" "$(cat /var/lib/chiron/bios-grub.stamp 2>/dev/null | cut -c1-12)… on the disk behind /boot"
check "mdadm" "$(grep -hE '^[[:space:]]*AUTO' /etc/mdadm/mdadm.conf 2>/dev/null || echo 'no AUTO line')"
check "LVM" "$(lvmconfig activation/auto_activation_volume_list 2>/dev/null || echo 'auto_activation_volume_list not set')"
check "time sync" "chrony $(systemctl is-active chrony), timesyncd $(systemctl is-active systemd-timesyncd 2>/dev/null || true)"
check "active rtcsync lines" "$(grep -rhE '^[[:space:]]*rtcsync' /etc/chrony 2>/dev/null | wc -l)"
check "RTC in local time" "$(timedatectl show -p LocalRTC --value)"
check "hwclock writers in /etc" "$(grep -rlsE 'hwclock.*(--systohc|-w([[:space:]]|$))' /etc | tr '\n' ' ' || true)"
for home in /home/*; do
  [ -d "$home" ] || continue
  u=$(stat -c %U "$home"); uid=$(id -u "$u" 2>/dev/null) || continue
  if [ -S "/run/user/$uid/bus" ]; then
    v=$(for p in /automount-drives/enabled /automount-media/enabled; do
          runuser -u "$u" -- env DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$uid/bus" xfconf-query -c thunar-volman -p "$p"
        done | tr '\n' ' ')
  else
    v="$(grep -c 'value="false"' "$home/.config/xfce4/xfconf/xfce-perchannel-xml/thunar-volman.xml" 2>/dev/null || echo 0) of 2 off"
  fi
  check "automount drives/media ($u)" "$v"
done
check "udisks: mount internal disk" "$(pkaction --verbose --action-id org.freedesktop.udisks2.filesystem-mount-system 2>/dev/null | sed -n 's/.*implicit active: *//p')"
check "swap" "$(swapon --show=NAME,SIZE --noheadings | tr -s ' ' | tr '\n' ' ')"
check "kernel" "running $(uname -r), newest $(ls /boot/vmlinuz-* | sort -V | tail -n1 | sed 's|/boot/vmlinuz-||')"

step "13. Snapshot base-configured"
snapshot base-configured
echo; echo "Phase 3 base configuration done."
