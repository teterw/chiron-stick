# Changelog

All notable changes to Chiron Stick are listed here.

## [Unreleased]

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
