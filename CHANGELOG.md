# Changelog

All notable changes to Chiron Stick are listed here.

## [Unreleased]

### Added
- **Chiron Doctor** (`chiron doctor`, in the dock and the menu): every check from one window, as a star chart styled like professional monitoring software. A command palette starts a run (keys `1`–`4`, arrows, Enter); every check is a node on the chart: a light travels along the link to it, a thin arc turns while it is checked, then it takes its status colour (`● OK`, `● WARN`, `● FAIL`) and its finding fades in, while the activity log records each event. The events are played back at a steady pace, so even a check that takes two seconds plays out node by node. During the stress test the centre shows the CPU's temperature, clock and time left with a temperature trace; then the diagnosis, what changed since the last check, and the owner summary one key away. Click a node for its findings. The checks run as root through the system's password dialog (asked once, remembered a few minutes); Stop, or closing the window, ends a test safely
- **Done alert**: a check that took a minute or longer (the stress test) ends with a desktop notification ("Check finished · Problem found · 13 checks · 10:21"), the sound theme's "complete" sound, and a taskbar flash if the window is behind others, so you can walk away during the test
- **What to do**: every amber or red finding comes with a next step and, when something needs replacing, the part to look for ("Back up the owner's files now, then replace the drive. Part: SATA SSD, 240 GB or larger", "Battery SMP AP18C8K · Li-ion · 48 Wh"). In the report (a list at the top), the owner summary (parts to get, Thai and English) and Chiron Doctor (each node's card, and the log at the end)
- `chiron --events`: machine-readable progress (JSON lines) for report, stress and full; a `stop` line on stdin stops the run safely
- **One password:** after the disk passphrase at boot, the desktop opens by itself (LightDM auto-login, `setup/50-rice.sh`). The screen locks after 10 minutes idle, on suspend and when the lid closes; `Super+L` locks it right away
- **See-through terminal** like GNOME's Ptyxis: 85% opaque with desktop effects on. Bright wallpapers showing through can't make text hard to read: the terminal's colours are lightened until they keep the theme's contrast (7:1 text, 4.5:1 colours), and only if that can't work does the terminal get less see-through
- **Soft window shadows**, GNOME-like: a small `Chiron-wm` window theme (Mint's Default with bigger shadows; xfwm4 only takes shadow sizes from a theme)
- Keys: `Super+M` minimise all windows (again: bring them back), `Super+←/→` half the screen, `Super+↑` maximise, `Super+↓` minimise, `Super+Q` close, `Super+L` lock, `Print` / `Shift+Print` screenshot of the screen / an area straight to `~/Pictures/Screenshots`. They replace Mint's `Ctrl+Alt+D`, `Super+keypad ←/→`, `Alt+F10` and `Alt+F9` (xfwm4 keeps one key per action); `Alt+F4` still closes

### Fixed
- Two checks of the same PC in the same minute wrote into one report folder, so the second replaced the first: the second now goes to `…-2`
- **Blurry boot menu and boot splash on big monitors:** GRUB kept the mode the PC's firmware was in, often 1024×768 or 800×600 on desktops, and the monitor stretched it. GRUB now uses 1920×1080 when the graphics card offers it (the splash keeps GRUB's mode). The menu picture is scaled to the screen's height instead of stretched, so the logo stays round on 4:3 and 16:10 screens
- Boot menu text: with Secure Boot, GRUB refuses to load font files, so it was drawing everything in its built-in pixel font. The countdown is now a thin violet bar, and the key hint is drawn smoothly into the picture. The menu entries themselves can only use the built-in font
- No `Super+key` window shortcut ever worked (Mint's `Super+Tab` and `Super+keypad` tiling included): Mint opens the menu with a bare `Super` binding, which grabs the keyboard while Super is held. A tap of Super now goes through `xcape` (it sends `Alt+F1`, which opens the menu), so tapping Super still opens the menu

## [0.7.0] - 2026-10-04

### Added
- Remove a wallpaper you don't like straight from the picker (`Super+W`): **Delete** or the **✕** on the picture. It drops away, the next one slides in, and it's removed the same way as in `chiron walls review` (gone after updates too). **Ctrl+Z** brings it back exactly as it was. Remove the wallpaper that's on your desktop and Esc uses the one on show instead of going back

## [0.6.0] - 2026-10-04

New wallpapers, picked by Tete: the first collection had many AI-captioned and AI-looking pictures.

### Added
- Wallpaper collections in `rice/wallsources.conf`, downloaded by `chiron walls update` into `~/Pictures/walls/<name>/`:
  - **Real space images**: 57 of ESA/Webb's and ESA/Hubble's top-rated pictures (wallpaper versions, CC BY 4.0), each pinned to its SHA-256 in `rice/space-walls.txt` with its title and credit
  - **Real photos**: elementary OS and Pop!_OS wallpapers
  - **Violet themes**: Rosé Pine (CC0) and Dracula (MIT)
  - **Aesthetic art**: D3Ext/aesthetic-wallpapers (MIT)
  - git collections are partial clones with a sparse checkout of their picture folders only
- `chiron walls review`: every new wallpaper one at a time, shown whole with its credit, with **Keep** and **Remove** buttons (→/Y, ←/N), Undo and Stop. Choices are saved as you go, and removed pictures stay gone after updates. A held key or a double-click counts once
- `chiron walls status`; *Wallpapers* and *Review wallpapers* in the app menu
- Folders of your own in `~/Pictures/walls/` join the collection
- Tests for the collections, the review exclusions and the space list

### Changed
- The dock is a floating pill with rounded ends and a thin accent outline, and the top bar's islands are rounder. Without a compositor (VMs, PCs without graphics drivers) the dock's background is the slice of wallpaper behind it, so the rounded corners still show
- Client mode uses space, elementary, Pop!_OS and Rosé Pine photography
- The picker shows each picture's collection and title (space images by name)

### Removed
- The dharmx/walls collection (3 GB) and `rice/get-walls.sh`; `chiron walls update` removes the old download

## [0.5.0] - 2026-10-04

A new look picked by Tete: the constellation logo in Chiron violet, and a wallpaper switcher in the style of Arch Linux rices.

### Added
- `rice/chiron-walls`: the full-screen wallpaper picker (`Super+W`). It opens by shrinking the current wallpaper into a preview card, shows a live mock of the desktop and the palette in each wallpaper's colours (they morph as you browse), searches as you type, and on Enter grows the card into your new desktop. Esc goes back the same way. rofi stays as a fallback
- Animated wallpaper changes behind the windows, like swww: grow from the mouse pointer, wipe, wave or fade, with the theme recolouring halfway through. Used by `random` (`Super+Shift+W`), the 30-minute rotation, `apply` and `mode`. `chiron rice animations on|off`
- New logo: a constellation (six stars forming a C, and Sagittarius' arrow) on a violet night sky, on the boot menu, the boot splash (stars twinkle while it boots; the arrow's star flares at the end), the login screen and in the terminal (braille)
- Login screen theme `Chiron-greeter` (violet instead of the default blue)
- `setup/12-boot-tests.sh`: `SHOT_EVERY=N` saves a screenshot every N seconds (boot menu, splash)
- Tests for reading wallust's colours and the palette cache

### Changed
- The brand accent is Chiron violet `#8b5cf6` instead of teal: boot screens, login screen, and the accent for grey wallpapers
- wallust prints the 16 colours with no config, no templates and no cache of its own (it had grown to 190 MB); chiron-rice keeps a tiny cache, so preview and result always match
- Re-theming takes 0.7 s instead of 2.2 s: conky restarts without being waited for
- `setup/50-rice.sh` skips downloads that are already installed and ends with the Timeshift snapshot `riced`

### Fixed
- Boot menu on legacy-BIOS PCs (GRUB runs at 640×480 there): entries were cut off
- After a boot that never finished (e.g. powered off at the unlock prompt) the boot menu waited 30 s instead of 5
- The console GRUB shows while loading the kernel covered 70% of the screen; it's now a smaller box with a thin violet edge (GRUB keeps it black and centred)
- The boot splash could show leftover frames of Mint's logo

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
