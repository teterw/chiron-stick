# Changelog

All notable changes to Chiron Stick are listed here.

## [Unreleased]

## [0.2.0] - 2026-10-04

Phase 2: Linux Mint 22.3 Xfce is installed on the SSD (UEFI + BIOS boot partitions, encrypted btrfs root) and boots in the VM with Secure Boot enabled.

### Fixed
- `setup/02-create-vm.sh`: keep the ISO attached and boot it first across restarts (`--import` with the ISO as a CD drive). With `--cdrom`, virt-install dropped the ISO after the first boot, so a restart during the install had nothing to boot.

### Docs
- Phase 2 checklist: choose each partition's "Use as" when creating it (changing it later can leave the EFI partition unformatted and freeze the installer), how to recover, and leave "Encrypt my home folder" unticked

## [0.1.0] - 2026-10-03

Phase 1: the build host and VM are ready. The VM boots the Linux Mint 22.3 live ISO with Secure Boot enabled.

### Added
- Project plan (`CLAUDE.md`): goals, scope, safety rules, and the phase-by-phase build guide
- README with the planned `chiron` command set
- MIT license
- Phase 1 setup scripts, all with `--dry-run`:
  - `setup/00-host-prep.sh`: Fedora host tools, libvirt access, no automount of the target SSD
  - `setup/01-get-mint-iso.sh`: download Linux Mint 22.3 Xfce and verify its GPG signature and SHA256
  - `setup/02-create-vm.sh`: build VM with Secure Boot (Microsoft 2011 + 2023 CAs) and the target SSD passed through, after safety checks (USB, drive serial, size, nothing mounted)
  - `setup/lib/common.sh`: shared safety checks
