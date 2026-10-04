# Chiron Stick

A portable Linux "PC doctor" on a USB SSD. Plug it into a PC or laptop (with the owner's consent), boot from it, and get a clear **green / yellow / red** health report on the battery, storage, RAM, CPU and cooling, GPU, sensors and hardware errors. Then unplug it, and the machine is left exactly as it was.

Named after Chiron, the wise centaur of Greek myth, a healer and teacher.

> **Status:** in development. The stick boots with Secure Boot, the health-check commands work and the desktop theme is done; real-hardware testing is next.

## The `chiron` command

Everything Chiron Stick adds is one command, `chiron`.

| Command | What it does |
|---|---|
| `chiron report` | Read-only health check (about 3 minutes) |
| `chiron stress [--minutes 10]` | Load tests with live safety limits |
| `chiron full` | Report + stress tests + one combined verdict |
| `chiron compare` | Compare this machine with its previous report |
| `chiron mount-ro <device>` | Mount one of the owner's partitions read-only (BitLocker only with a recovery key the owner types) |
| `chiron forget <machine>` | Delete every stored report for one machine |
| `chiron rice apply <image>` | Set a wallpaper and re-theme the whole desktop from its colors |
| `chiron rice pick` / `chiron rice random` | Choose a wallpaper (also `Super+W` / `Super+Shift+W`) |
| `chiron rice mode client\|personal` | Calm wallpapers on other people's PCs, or the full set for personal use |
| `chiron rice pause` / `chiron rice resume` | Pause wallpaper rotation and desktop effects (stress tests do this automatically) |
| `chiron walls update` | Download or update the wallpaper collection |
| `chiron help` | List every command |

## What it checks

- **Battery:** health vs. its original capacity, charge cycles, estimated runtime
- **Storage:** SMART health, wear, errors, temperature, read speed (read-only)
- **RAM:** quick memory test, plus hardware memory errors in the kernel log
- **CPU and cooling:** temperatures and throttling under load, fans
- **GPU:** a short graphics test
- **Free space** on the installed OS (mounted read-only)
- **Windows 11 readiness** and Secure Boot certificate status
- **Device support:** tells "no Linux driver on this stick" apart from "actually broken"

Each run produces a technical report (Markdown, HTML, JSON) and a one-page **owner summary in Thai and English**.

## The desktop

"Clinic Night" is a dark Xfce desktop that takes its colors from the wallpaper. `Super+W` opens a full-screen picker: browse the wallpapers and see a live preview of the whole desktop in each one's colors, then press Enter and the preview grows into your new desktop. The panel, windows, terminal, app launcher, notifications and folder icons all follow. Other wallpaper changes slide in behind your windows with animated transitions (grow, wipe, wave or fade). Every color is contrast-checked, so text stays readable on any wallpaper. The reports' green, yellow and red never change with it. The desktop idles at about 0.9 GB of RAM, and turns its effects off on PCs without working graphics drivers. Wallpapers come from [dharmx/walls](https://github.com/dharmx/walls) (`chiron walls update`).

The logo is a constellation: six stars forming a C, with Sagittarius' arrow flying out of it (in the myth, Chiron became that constellation). It's on the boot menu, boot splash and login screen, in Chiron violet.

## Leaves no trace

- Boots with Secure Boot **on**, using only Microsoft- and Canonical-signed boot files: no BIOS changes, no key enrollment
- Never adds firmware boot entries and never writes the hardware clock
- Never mounts the owner's disks read-write; speed tests are read-only
- No SSH server and no automounting

## Supported hardware

- **Yes:** x86-64 Intel/AMD desktops and laptops from roughly the last 10–15 years. UEFI with Secure Boot (main target), UEFI without it, and legacy BIOS (best effort).
- **No:** Apple Macs, ARM Windows laptops, Chromebooks, 32-bit-only PCs, locked school/office PCs, and PCs whose firmware has the Microsoft third-party UEFI CA turned off (e.g. Microsoft Surface, some Lenovo "Secured-core" models).

## Consent and ethics

Only use Chiron Stick on a machine whose owner has agreed. The owner types any passwords or BitLocker keys themselves, their files are only read if they ask, and reports can be deleted on request (`chiron forget`). Password reset or bypass tools are deliberately not included.

## Build your own

A step-by-step guide (`docs/INSTALL.md`) is coming. You'll need a 120 GB+ SSD in a USB 3 enclosure and a Linux PC that can run virtual machines (KVM). Chiron Stick is built on Linux Mint 22.3 Xfce.

The build is scripted in `setup/`, one script per step. Each script has a `--dry-run` mode that only prints what it would do:

On the Fedora host:

1. `sudo setup/00-host-prep.sh <drive-serial>`: prepare the host
2. `setup/01-get-mint-iso.sh`: download and verify the Mint ISO
3. `setup/02-create-vm.sh /dev/disk/by-id/usb-... <drive-serial>`: create the build VM with the SSD passed through
4. Install Mint in the VM by hand (the checklist is in `CLAUDE.md`, Phase 2)

On the stick (in the VM, as root, from a copy of this repo):

5. `setup/10-base-config.sh`: boot safety (pinned Secure Boot shim, no firmware or clock writes, no os-prober, no automount), updates, snapshots
6. `setup/20-toolkit.sh`: the diagnostic tools
7. `setup/30-chiron.sh`: the `chiron` command
8. `setup/40-memtest86.sh`: MemTest86 in the boot menu (downloaded and signature-checked; never redistributed)
9. `setup/50-rice.sh`: the desktop theme's system part (packages, checksum-verified downloads, boot and login screens)
10. `setup/51-rice-user.sh`, as the desktop user inside the desktop session: panels, keys and theme. Then `chiron walls update` downloads the wallpapers (about 3 GB).

Back on the host: `setup/12-boot-tests.sh` boots the stick in fresh UEFI (Secure Boot) and legacy-BIOS test VMs.

Find your drive's serial with `lsblk -o NAME,SIZE,MODEL,SERIAL,TRAN`. How to use the finished stick: [docs/USAGE.md](docs/USAGE.md).

> ⚠️ **The setup erases the target disk.** The scripts check the disk (USB connection, size, model and serial) and make you type `yes`, but picking the wrong disk destroys its data. Read every prompt.

## License

MIT. Wallpapers aren't included: `chiron walls update` downloads them from their source, and credit belongs to the original artists.
