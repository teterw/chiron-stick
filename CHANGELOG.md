# Changelog

All notable changes to Chiron Stick are listed here.

## [Unreleased]

### Changed
- `setup/50-rice.sh` ends with the Timeshift snapshot `riced`, like the earlier setup scripts

## [0.4.0] - 2026-10-04

Phase 4R: the "Clinic Night" desktop theme. The whole desktop takes its colours from the wallpaper.

### Added
- `setup/50-rice.sh` (system part) and `setup/51-rice-user.sh` (per user); the engine is `rice/chiron-rice`
  - `chiron rice apply <image>` re-themes GTK programs, the panels, terminal, rofi, notifications, btop, conky, starship, fastfetch and folder icons from the wallpaper in under 3 s. Contrast is checked, so any wallpaper gives readable text; grey wallpapers get Chiron teal. If anything fails, the previous theme stays.
  - A top bar of "islands" and an auto-hiding dock (`rice/panel-layout.json`)
  - Wallpaper picker with thumbnails (`Super+W`), random wallpaper (`Super+Shift+W`), app launcher (`Super+D`), terminal (`Super+Return`)
  - `chiron rice mode personal` (whole collection, new wallpaper every 30 minutes) and `client` (calm wallpapers, no rotation)
  - `chiron walls update` downloads the dharmx/walls collection without its animated wallpapers
  - conky system-stats widget (a user service that restarts itself if it crashes), fastfetch with a Chiron logo, starship prompt
  - Boot and login branding: GRUB theme, Plymouth splash, slick-greeter background
  - Checksum-pinned downloads (adw-gtk3, fastfetch, starship, JetBrainsMono Nerd Font); wallust built from crates.io with `--locked`, then the Rust toolchain is removed
  - Builds the icon caches Mint's Papirus lacks: idle RAM 1.8 GB → 0.9 GB
- Tests for colour contrast on dark, bright and grey palettes, the panel layout, and "no half-applied theme"

### Changed
- `chiron stress` only resumes the desktop theme if it paused it, so a pause you set yourself stays

## [0.3.0] - 2026-10-04

Phases 3, 4 and 6 done, and the `chiron` tool works in the build VM. The stick boots on fresh UEFI firmware (Secure Boot on, no boot entries) and on legacy BIOS; MemTest86 runs from its boot menu with Secure Boot on.

### Added
- Phase 6, `setup/40-memtest86.sh`: MemTest86 Free in the boot menu (UEFI). Downloaded by each builder (its licence grants no redistribution) and checked against Microsoft's UEFI CA 2011 signature, since no checksum is published
- `setup/12-boot-tests.sh`: boots the stick in throwaway VMs with fresh UEFI (Secure Boot) firmware and with legacy BIOS
- Phase 3, `setup/10-base-config.sh`: pinned 2011-signed shim on the removable path, `grub-install` wrapper (no NVRAM writes, no `fbx64.efi`), legacy-BIOS GRUB, no os-prober, efi-pstore off, no RAID/LVM auto-start, chrony without `rtcsync`, no automount, zram, Timeshift snapshots
- Phase 4, `setup/20-toolkit.sh`: the diagnostic tools (installed without recommends; smartd masked; smoke test)
- Phase 5, the `chiron` tool (v0.3.0): `report`, `stress`, `full`, `compare`, `mount-ro`/`umount`, `forget`, `help`
  - Checks: system, battery, storage (SMART, temperature, read-only speed test), memory, CPU (against its own Tjmax), sensors, kernel hardware errors, device support (works / no driver here / driver errors), free space on the PC's own OSes (read-only mounts), Windows 11 readiness, Secure Boot certificates, firmware updates (read-only)
  - Owner summary in Thai and English; technical report as Markdown, HTML and JSON; per-machine history with salted fingerprints
  - Windows 11 CPU check against Microsoft's 25H2 supported-processor lists (`tools/update-win11-cpus.py` refreshes them)
  - Unit tests for the grading logic; opt-in smoke tests (`CHIRON_SMOKE=1`)
- `setup/30-chiron.sh`: installs the tool to `/opt/chiron` and the `chiron` command
- `docs/USAGE.md`: consent checklist, boot keys by brand, commands, leaving without a trace

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
