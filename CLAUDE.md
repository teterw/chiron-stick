# Chiron Stick — Project Plan

> **How to use this file**
> 1. Put this file in an empty folder on the Fedora laptop, e.g. `~/projects/chiron-stick/CLAUDE.md`.
> 2. Run `claude` from that folder. Claude Code loads `CLAUDE.md` automatically every session, so the safety rules below are always active.
> 3. Paste the **Starter prompt** (section 10a, at the bottom) as your first message.
> 4. Keep private details (your machines, the drive's serial, username and hostname) in `CLAUDE.local.md` next to this file. Claude Code loads it automatically, and it's gitignored.
>
> This is an **open-source project**: everything gets published to GitHub as it's built (section 5b).
>
> Facts in this file were checked in October 2026. Claude Code: re-verify versions and package names before using them.

---

## 1. What we're building

**Chiron Stick**: a portable Linux "PC doctor" on a 120 GB SSD in a USB enclosure. (Chiron is the wise centaur of Greek myth, a healer and teacher.)

Plug it into a consenting owner's PC or laptop → boot from USB → run a hardware health check plus stress tests → get a clear **green / yellow / red** report. Then unplug and leave the owner's machine **exactly as it was**.

**Roles**
- **Tete** (owner of this project): physical steps, the GUI installer, booting real PCs, all passwords, final decisions.
- **Claude Code**: setup engineer. Prepares the host, builds the VM, configures the installed system over SSH, and co-writes the `chiron` tool with Tete.

---

## 2. Scope

### In scope (v1)
- x86-64 Intel/AMD desktops and laptops, roughly the last 10–15 years
- UEFI with **Secure Boot ON** (main target), UEFI without Secure Boot, legacy BIOS (best effort)
- Machines running Windows or Linux (hardware checks don't depend on the installed OS)
- **Health report:** battery, storage, RAM, CPU and cooling, GPU, sensors, hardware errors in the kernel log, hardware inventory
- **"How is it holding up" tests:** CPU load + thermal throttling, storage speed, RAM, GPU, battery runtime estimate
- Read-only inspection of the owner's drives (BitLocker only with a recovery key the owner types in)
- Copying files *off* a failing drive, only when the owner asks
- **Desktop rice (Tete's part):** a heavily personalized Xfce desktop whose whole theme follows the current wallpaper (Phase 4R)

### Out of scope
- All Apple Macs, ARM Windows laptops (Snapdragon), Chromebooks, 32-bit-only PCs
- Locked or managed school/office PCs
- Windows software repair (sfc, DISM, Startup Repair) → a later phase (Windows PE partition)
- Password reset/bypass tools — **deliberately not included**
- Proprietary NVIDIA drivers (they would need per-machine key enrollment under Secure Boot)
- The NAS project with the other two SSDs (separate project)
- Any use without the machine owner's consent

---

## 3. Known facts and environment

| Item | Value |
|---|---|
| Host (where Claude Code runs) | A Fedora laptop with KVM (details in `CLAUDE.local.md`) |
| Second own machine for testing | A Windows desktop (details in `CLAUDE.local.md`) |
| Target drive | WD Green 120 GB, **M.2 2280 SATA** (B+M key). Not NVMe. |
| Enclosure | HIKSEMI MD202 (HS-HUB-MD202), Realtek RTL9210B bridge, USB 3.2 Gen 2 Type-C |
| Cable | USB-C, USB 3.2 10 Gbps |
| Link speed | A 10 Gbps USB-C port with a C-to-C cable gives `10000M`; many USB-A ports give `5000M`. A half-seated USB-C plug can fall back to USB 2.0 (480M): reseat it. |
| Distro | **Linux Mint 22.3 "Zena" Xfce** (Ubuntu 24.04 base, Ubiquity installer, supported to 2029) |
| Future | Mint 23 (Ubuntu 26.04 base, new installer) is expected around Dec 2026 → upgrade or reinstall later |
| Timezone | Asia/Bangkok (UTC+7) |
| Wallpapers | https://github.com/dharmx/walls: ~1,700 files in ~55 category folders (mostly jpg/png, plus 11 `.mp4` in `animated/`). Total size not measured yet: measure after cloning. The repo owner notes the images were collected from many sites and credits belong to the original artists: personal use only, don't redistribute. |
| Theming engine | **wallust** (pywal successor: 16-color palette from an image, template system, `check_contrast` option). Not in apt: install a release binary (verify checksum) or build with cargo. |

### Claude Code must check these itself (don't assume)
- Host RAM, CPU, virtualization support (`/dev/kvm`, vmx/svm flags), free disk space, Fedora version
- Whether the target drive is connected, its `/dev/disk/by-id/usb-…` path, that its serial matches `CLAUDE.local.md`, and whether the host auto-mounted any of its partitions

### Ask Tete (never store secrets)
- LUKS passphrase and sudo password: Tete types them interactively. They never go into any file, script, log, or command line.

---

## 4. Key decisions (and why)

1. **Full install, not a live ISO with persistence.** Real package manager, real updates, our own tools.
2. **Install inside a VM on the host, with the whole USB disk passed through.** The installer can only see the target disk. The host's internal NVMe and the host's firmware boot entries are out of reach.
3. **Secure Boot stays ON everywhere.** Only the Microsoft/Canonical-signed boot chain is used, so no key enrollment is needed on other people's PCs and no BIOS settings get changed (changing them can trigger BitLocker recovery).

   **Which shim (decided October 2026).** Microsoft's UEFI CA 2011, which signs shim, expired in June 2026. Shims released after that are signed only with the UEFI CA 2023. Firmware ignores expiry dates, and many PCs from the last 10–15 years (especially Windows 10 PCs that no longer get updates) still trust only the 2011 CA, while updated PCs trust both. So:
   - `EFI/BOOT/BOOTX64.EFI` is the **2011-signed shim, pinned** (verified copy in `/usr/local/share/chiron/shim-2011/`). Every PC boots this by default.
   - `EFI/ubuntu/` stays managed by apt. When Ubuntu ships the 2023-signed shim, it lands there. On a PC that trusts only the 2023 CA, choose "Boot from file → `EFI/ubuntu/shimx64.efi`" in the firmware's one-time boot menu (no settings change).
   - `grubx64.efi` and `mmx64.efi` in `EFI/BOOT/` still get updates (`chiron-efi-sync` copies them from `EFI/ubuntu/`), so GRUB security fixes apply.
   - `chiron report` shows which Microsoft CAs each PC trusts.
   - Revisit at Mint 23, or if Microsoft revokes the pinned shim.
4. **Partition layout (GPT):**

   | # | Size | Type | Mount | Notes |
   |---|---|---|---|---|
   | 1 | 600 MB | EFI System (FAT32) | `/boot/efi` | |
   | 2 | 1 MB | BIOS boot | — | for legacy-BIOS GRUB |
   | 3 | 1024 MB | ext4 | `/boot` | unencrypted so both UEFI and BIOS GRUB can read it |
   | 4 | 105,000 MB (~98 GiB) | LUKS2 → btrfs | `/` (subvolumes `@`, `@home`) | encrypted: the drive is easy to lose and may hold reports about other people's machines |
   | — | ~13 GB | **unallocated** | — | reserved for the Windows PE partition (later) |

5. **btrfs + Timeshift snapshots** so any bad change can be rolled back.
6. **Generic initramfs.** Mint/Ubuntu default is `MODULES=most` (includes drivers for most hardware). Verify it; never switch to `dep`.
7. **"Leave no trace" on host machines:**
   - Boot via the removable path `EFI/BOOT/BOOTX64.EFI` (= the pinned shim, decision 3) + `grubx64.efi` + `mmx64.efi`. **No `fbx64.efi` in `EFI/BOOT`**: shim's fallback would write boot entries into the owner's firmware.
   - GRUB packages must never write firmware boot entries (`grub2/update_nvram = false`). `EFI/BOOT/` is maintained by our APT hook `chiron-efi-sync`, not by grub-install (`grub2/force_efi_extra_removable = false`).
   - **os-prober off** (`GRUB_DISABLE_OS_PROBER=true`). Mint turns it on; then any `update-grub` run while plugged into an owner's PC would scan their disks and add their OS to our boot menu.
   - **No NVRAM writes from the kernel:** efi-pstore disabled (`efi_pstore.pstore_disable=1`), so a crash during a stress test can't store logs in the owner's firmware.
   - **No auto-start of the owner's RAID arrays or LVM volumes** (starting an array can write to its disks).
   - **Clock:** Windows keeps the hardware clock (RTC) in local time; Linux assumes UTC. Never write the RTC, or the owner's Windows clock will be 7 hours off after we leave. Replace systemd-timesyncd with **chrony without `rtcsync`**. No `hwclock --systohc` anywhere.
   - No automount of internal disks. Every inspection mount is read-only.
   - No SSH server on the finished drive.
   - SMART is read-only (`smartctl -a`/`-x`). No SMART self-tests on owner drives unless the owner asks (they add entries to the drive's log), and the `smartd` service is disabled.
8. **Kernel:** newest Ubuntu 24.04 HWE kernel, for the best support of new hardware.
9. **Tool language:** Python 3 (standard library; optionally `python3-rich`) wrapping standard Linux CLI tools.
10. **Rice principles** (details in Phase 4R):
    - **The doctor comes first.** The rice must never make the drive fail to boot, slow it down badly, or skew test results. Everything must work on old PCs, VMs and software rendering.
    - **Verdict colors are fixed.** Green/yellow/red in `chiron` output and reports never come from the wallpaper palette, so a red result always looks red.
    - **Client mode vs personal mode.** On someone else's PC, show a calm, neutral wallpaper set. The full collection is for personal use.
    - **Tests run "clean".** `chiron stress`/`full` pause wallpaper rotation and the compositor, then restore them afterwards.
11. **One command: `chiron`.** Everything the project adds for the user is a subcommand of `chiron` (`chiron report`, `chiron rice apply`, `chiron walls update`, …), listed in the README and by `chiron help`. Internal helpers (APT hooks, setup scripts) use a `chiron-` prefix, e.g. `chiron-efi-sync`.

### Known limitations (accepted)
- A brand-new laptop may need a newer kernel for Wi-Fi or graphics.
- NVIDIA GPUs run on the open `nouveau` driver: basic display only. Enough for diagnostics.
- Booting any current signed shim can update the machine's Secure Boot revocation variable (SBAT). This only affects very outdated Linux bootloaders on that machine; Windows is unaffected. It can't be avoided with Secure Boot on.
- SMART "PASSED" is not a guarantee. Drives sometimes fail without warning.
- Some newer PCs (Microsoft Surface, many Lenovo "Secured-core" models) ship with the Microsoft third-party UEFI CA turned off. The stick can't boot there with Secure Boot on unless a firmware setting is changed, so skip those machines.
- A PC that trusts only the Microsoft UEFI CA 2023 needs the one-time "Boot from file" step (decision 3).
- Timeshift (btrfs mode) doesn't snapshot `/boot` (separate ext4). After rolling back across a kernel update, reinstall the running kernel package so `/boot` matches `/`.

---

## 5. SAFETY RULES for Claude Code (non-negotiable)

1. **The host's internal disk** (e.g. `/dev/nvme0n1`, or anything `lsblk` shows with `TRAN` ≠ `usb`) must **never** be the target of: partitioning, formatting, `dd`, `wipefs`, `mkfs`, `sgdisk`, `parted` (write), `cryptsetup luksFormat`, read-write mounts, or `grub-install`.
2. **On the host, refer to the target drive only via its `/dev/disk/by-id/usb-…` path.** Before any destructive command, run and show `lsblk -o NAME,SIZE,MODEL,SERIAL,TRAN,MOUNTPOINTS` and `readlink -f <by-id path>`, and confirm: `TRAN=usb`, size ≈ 111.8 GiB, model contains `WD`/`WDS120`, and **the drive serial matches `CLAUDE.local.md`** (the by-id name only identifies the enclosure, and enclosures of the same brand can share it). If any check fails → **STOP**.
3. **Destructive commands:** print the exact command and what it will destroy, then wait for Tete to type `yes`.
4. Never have the target's partitions mounted on the host while the VM is running. Never run two VMs that use the target disk at the same time.
5. **Secrets:** never write passwords or the LUKS passphrase into files, scripts, logs, or command arguments.
6. **Temporary conveniences** (passwordless sudo, SSH server, SSH keys, test accounts) must be listed in `PROGRESS.md` under **"Temporary — remove before done"** and removed in Phase 8.
7. No `curl | sh`. Verify every download (SHA256, plus GPG signature where the vendor provides one).
8. Log every change in `PROGRESS.md`: date, phase, what changed, how it was verified.
9. When a step needs Tete (GUI clicks, plugging things in, booting other PCs), stop and give numbered instructions, then wait.
10. When unsure: investigate read-only first, then ask.
11. **Unplugging:** power the drive off first (`udisksctl power-off -b <by-id path>`). This cheap SSD has no power-loss protection.
12. **Updates** (`apt upgrade`, anything touching shim, GRUB or the kernel) run only on Tete's own machines or in the VM, never on an owner's PC. After such an update, test-boot the stick in the VM (Secure Boot on) before using it on anyone's PC.

---

## 5b. Open source: publish to GitHub as we go

This project is public so others can build their own Chiron Stick. **Rule: if it isn't in the repo, it doesn't exist.** Every config change, script, command and feature must end up in the repo in a form someone else can reproduce.

### Repo setup (Phase 1)
- Repo name **`chiron-stick`**, license **MIT** (decided). Tete runs `gh auth login` himself; Claude Code never handles tokens.
- Suggested layout:

  | Path | Contents |
  |---|---|
  | `README.md` | What it is, the `chiron` command list, screenshots, supported/unsupported hardware, consent and ethics note, quick start |
  | `docs/INSTALL.md` | Full reproducible build guide, including the Phase 2 GUI checklist |
  | `docs/USAGE.md` | How to boot it and run `chiron` |
  | `setup/` | One idempotent script per phase (`10-base-config.sh`, `20-toolkit.sh`, …) with a `--dry-run` flag |
  | `chiron/` | The `chiron` tool (every user command) |
  | `rice/` | wallust config and templates, rice scripts (run through `chiron rice …`), configs. Wallpapers are **downloaded by `chiron walls update`, never committed** |
  | `CHANGELOG.md`, `LICENSE`, `.gitignore` | |

- Personal details (this laptop, drive serial/by-id path, username, hostname) stay out of the public repo. They live in `CLAUDE.local.md` (gitignored; Claude Code loads it automatically next to `CLAUDE.md`). `PROGRESS.md` is gitignored too; the public history lives in `CHANGELOG.md`.

### Publish workflow (every feature or command)
1. Implement it and test it (VM, or real hardware when relevant).
2. Turn any manual steps into the matching `setup/` script, and update `README.md` / `docs/` / `CHANGELOG.md`.
3. Show Tete `git status` and a summary of `git diff --staged`. Scan for secrets (e.g. `gitleaks`, if installed).
4. Commit with a clear message (`feat(chiron): add battery runtime estimate`, `fix(setup): …`), then push.
5. At the end of each phase: tag a release (`v0.1.0`, …) with short release notes.

### Never commit
- Passwords, LUKS details, SSH keys, tokens
- Reports, machine fingerprints, serial numbers, or anything about an owner's machine
- Wallpaper images (link to the source repo and download them by script instead)
- MemTest86 binaries (license): `setup/` downloads them
- Tete's personal details

### Safety for other people
`setup/` scripts that touch disks must use the **same checks as section 5**: by-id path, `TRAN=usb`, size check, type `yes` to continue. The README must warn clearly that choosing the wrong disk erases it. Commits and pushes happen from the host laptop's repo, never from the doctor drive (the drive holds no Git credentials).

---

## 6. Phases

Each phase has tasks and a **Done when** list. Claude Code must show the evidence for every Done-when item before moving on.

### Phase 0 — Pre-flight (host, read-only)
- Find the target: `lsblk -o NAME,SIZE,MODEL,SERIAL,TRAN,MOUNTPOINTS` and `ls -l /dev/disk/by-id/ | grep usb`
- Link speed: `lsusb -t` → expect `Driver=uas` and `5000M` or `10000M`
- Health: `sudo smartctl -d sat -a <by-id path>` (install `smartmontools` with dnf if missing). Record power-on hours, wear/remaining life, reallocated/pending sectors, CRC errors.
- Read speed (read-only): `sudo hdparm -t <by-id path>`
- Ask Tete whether anything on the drive needs backing up (it gets erased in Phase 2).
- If the drive held data before: once Tete agrees, TRIM it first (`blkdiscard`), then run a full write + read-back test. Overwriting a full, untrimmed cheap SSD is extremely slow.

**Done when:** by-id path recorded in `PROGRESS.md` · `uas` + ≥5000M confirmed · SMART summary recorded with a go / no-go verdict.

### Phase 1 — Host preparation
- Confirm virtualization: `/dev/kvm` exists and `grep -Ec '(vmx|svm)' /proc/cpuinfo` > 0
- Install virtualization packages (verify names on the current Fedora): `virt-manager`, `virt-install`, `virt-viewer`, `qemu-kvm`, `libvirt-daemon-kvm`, `edk2-ovmf`, `python3-virt-firmware`. Fedora uses libvirt's modular daemons (`virtqemud`, `virtnetworkd`, …), not `libvirtd`. Add the user to the `libvirt` group and add a udev rule so the host never automounts the target (script: `setup/00-host-prep.sh`).
- Download the **Linux Mint 22.3 Xfce 64-bit** ISO from an official mirror, plus `sha256sum.txt` and `sha256sum.txt.gpg`. Verify the GPG signature with the Linux Mint signing key (follow Mint's official verification guide), then verify the ISO checksum (script: `setup/01-get-mint-iso.sh`). Keep the ISO in `/var/lib/libvirt/boot/chiron/`: the VM can't read files in a home folder.
- Create VM `chiron-build` (`qemu:///system`, script: `setup/02-create-vm.sh`):
  - q35 machine, **UEFI with Secure Boot enabled and Microsoft keys enrolled**
  - Check the enrolled keys include both Microsoft UEFI CA 2011 and 2023 (e.g. `virt-fw-vars --print` on the VM's vars file), so both boot paths can be tested
  - 4 GiB RAM (less if the host has under 8 GiB), 2–4 vCPUs, NAT network
  - ISO as CD-ROM (boot first)
  - Target disk passed through as a **raw block device using its by-id path** (SATA or virtio-scsi bus)
- Unmount any host auto-mounts of the target's partitions before starting the VM.
- **Create the GitHub repo** following section 5b: layout, `.gitignore` (PROGRESS.md, CLAUDE.local.md, reports, wallpapers), LICENSE, a first README. Tete reviews before the first public push.

**Done when:** repo created and first commit pushed · ISO signature + checksum verified (show output) · relevant `virsh dumpxml` parts shown (secure-boot firmware, disk source = by-id path) · VM boots the Mint live ISO, and `mokutil --sb-state` in the live session says **SecureBoot enabled**.

### Phase 2 — Install Mint (Tete, GUI inside the VM)
Claude Code gives Tete this checklist, then waits.

1. In the live session, double-click **Install Linux Mint**.
2. Language: English. Keyboard: **English (US) only** (keeps the LUKS unlock prompt simple; Thai input can be added later).
3. Multimedia codecs: leave **unchecked**.
4. Installation type: **Something else**.
5. Select the ~120 GB disk (the only one) → **New Partition Table**.
6. From free space, create in this order:
   1. 600 MB → *Use as:* **EFI System Partition**
   2. 1 MB → *Use as:* **Reserved BIOS boot area**
   3. 1024 MB → **Ext4**, mount point **/boot**
   4. 105000 MB → *Use as:* **physical volume for encryption** → enter the passphrase (Tete chooses it and writes it down offline)
   5. Select the new `…_crypt` volume at the top of the list → **btrfs**, mount point **/**
   6. Leave the remaining ~13 GB as **free space**
7. Device for boot loader installation: the ~120 GB disk.
8. Timezone: Bangkok. Username and hostname from `CLAUDE.local.md`. Require a password to log in.
9. Finish → restart → Claude Code detaches the ISO → unlock with the passphrase → log in.

**Done when:** the installed system boots in the VM with Secure Boot on · `lsblk -f` matches the layout · `sudo parted <disk> unit GiB print free` shows ~12 GiB free at the end.

### Phase 3 — Base configuration (Claude Code over SSH into the VM)
**Access setup (Tete, in the VM terminal):** `sudo apt install openssh-server`, get the IP with `ip -4 a`, let Claude Code add a setup SSH key, and create a temporary passwordless-sudo file with `sudo visudo -f /etc/sudoers.d/99-chiron-setup`. Record all of these as **Temporary** in `PROGRESS.md`.

Inside the VM the target is simply the VM's only disk (e.g. `/dev/sda`).

1. **Updates:** first save the pinned shim (step 4, second bullet), so an upgrade can't replace it before it's copied. Then `sudo apt update && sudo apt full-upgrade`. Make sure the newest HWE kernel is installed (`linux-generic-hwe-24.04` or Mint's Update Manager). Show `uname -r`.
2. **Snapshot:** first check for a `/swapfile` the installer may have created and remove it with its `/etc/fstab` line (an active swapfile inside `@` blocks btrfs snapshots; zram replaces it in step 8). Then Timeshift in btrfs mode, with `@home` **not** included (so `chiron forget` really forgets) → snapshot `base-install`.
3. **Generic initramfs:** confirm `MODULES=most` in `/etc/initramfs-tools/initramfs.conf` and no override in `conf.d/`.
4. **Removable UEFI path with the pinned shim, no firmware writes** (decision 3):
   - Find the exact debconf keys with `sudo debconf-show grub-efi-amd64-signed` (and `grub-efi-amd64`). Set `grub2/update_nvram` = false and `grub2/force_efi_extra_removable` = false, then reconfigure GRUB.
   - Check who signed the installed shim: `sbverify --list /boot/efi/EFI/ubuntu/shimx64.efi` (package `sbsigntool`). If it's **Microsoft Corporation UEFI CA 2011**, save a copy as the pinned shim in `/usr/local/share/chiron/shim-2011/` with its SHA256 and the `shim-signed` version. If apt already installed a 2023-signed shim, use `EFI/boot/bootx64.efi` from the verified Mint 22.3 ISO instead (shim 15.8, signed via Microsoft Corporation UEFI CA 2011, checked 2026-10-03).
   - Install `/usr/local/sbin/chiron-efi-sync` plus an APT hook (`/etc/apt/apt.conf.d/99-chiron-efi`, `DPkg::Post-Invoke`). It makes `EFI/BOOT/` contain exactly: the pinned shim as `BOOTX64.EFI` (hash checked), the current `grubx64.efi` and `mmx64.efi` from `EFI/ubuntu/`, and **no** `fbx64.efi`. It logs every change.
   - Test: boot the VM with **fresh firmware variables** (no saved boot entries). It must boot via the removable path with Secure Boot on. Also boot `EFI/ubuntu/shimx64.efi` once from the firmware boot menu.
5. **Legacy BIOS boot:** `sudo apt install grub-pc-bin`, then `sudo grub-install --target=i386-pc <disk>`. Add an APT hook that re-runs this when `grub-pc-bin` is upgraded; the hook must find the disk from `/boot`'s parent device, not a hard-coded name. Test with a separate throwaway VM using SeaBIOS (legacy BIOS) and the same disk, only while `chiron-build` is shut down. Don't set the `pmbr_boot` flag unless a real BIOS-only PC refuses to boot (it can confuse some UEFI firmware).
6. **Clock (no RTC writes):** install `chrony` (replaces systemd-timesyncd). Remove every `rtcsync` line from `/etc/chrony/` (including `conf.d/` and `sources.d/`). Confirm timesyncd is disabled and nothing calls `hwclock --systohc`.
7. **No automount:** turn off Thunar volume-manager automount (`xfconf-query -c thunar-volman -p /automount-drives/enabled -s false`, same for `/automount-media/enabled`). Mounting internal disks must still require admin auth (udisks default).
8. **Swap:** `zram-tools` (zstd, ~50% RAM). No swap file or swap partition on the USB drive.
9. **Drivers:** keep `linux-firmware` current. **Do not** install proprietary NVIDIA drivers. Leave Driver Manager alone.
10. Optional: Thai input method (ask Tete).
11. **os-prober off:** create `/etc/default/grub.d/99-chiron.cfg` with `GRUB_DISABLE_OS_PROBER=true` (it loads after Mint's `50_linuxmint.cfg`, which turns os-prober on), then `update-grub`.
12. **No NVRAM writes from the kernel:** unless `/sys/module/efi_pstore/parameters/pstore_disable` already shows `Y`, add `GRUB_CMDLINE_LINUX_DEFAULT="$GRUB_CMDLINE_LINUX_DEFAULT efi_pstore.pstore_disable=1"` to `99-chiron.cfg`, then `update-grub`.
13. **No auto-start of owner RAID/LVM:** if `mdadm` or `lvm2` is installed, set `AUTO -all` in `/etc/mdadm/mdadm.conf` and `auto_activation_volume_list = []` in `/etc/lvm/lvm.conf`, then `update-initramfs -u`.
14. **Snapshot** `base-configured`.

**Done when:** output of every check shown · steps captured in `setup/10-base-config.sh` and pushed · `PROGRESS.md` updated · both snapshots exist.

### Phase 4 — Toolkit
Install, verifying package names on Mint 22.3 / Ubuntu 24.04:

| Purpose | Packages |
|---|---|
| Inventory | `inxi`, `lshw`, `hwinfo`, `dmidecode`, `pciutils`, `usbutils`, `i2c-tools` (decode-dimms), `edid-decode` |
| Storage | `smartmontools`, `nvme-cli`, `hdparm`, `fio`, `gsmartcontrol` |
| CPU, thermal, load | `lm-sensors`, `stress-ng`, `s-tui`, `htop`, `btop`, `sysstat`, turbostat/cpupower (linux-tools for the running HWE kernel) |
| RAM | `memtester` |
| GPU | `mesa-utils`, `vulkan-tools`, `glmark2` (check exact package name), `nvtop`, `intel-gpu-tools`, `radeontop` |
| Battery and power | `upower`, `acpi`, `powertop` (do **not** install TLP or anything that changes power settings) |
| Network | `iperf3`, `ethtool`, `iw` |
| Rescue and inspection | `gparted`, `testdisk` (includes photorec), `gddrescue`, `ntfs-3g`, `dislocker`, `exfatprogs`, `dosfstools`, `btrfs-progs`, `cryptsetup` |
| Firmware | `fwupd`: read-only use only (`fwupdmgr get-devices`). Never update an owner's firmware without explicit consent. |

Don't run `sensors-detect` on owner machines; rely on auto-loaded drivers (coretemp, k10temp, nvme, acpitz).

Disable the `smartd` service (`smartmontools` starts it): `chiron` reads SMART on demand, and a background daemon shouldn't touch owner drives.

**Done when:** all installed · smoke test in the VM (`inxi -Fxz`, `sensors`, `smartctl --scan`, `upower -e`) runs without errors (missing sensors in a VM are fine) · `setup/20-toolkit.sh` pushed · snapshot `toolkit`.

### Phase 4R — Desktop rice (Tete leads the look, Claude Code builds it)
Tete decides the aesthetics. Claude Code proposes options and implements them, and asks before big visual choices. Everything goes into `rice/` in the repo.

**Wallpapers**
- `chiron walls update` (script `rice/get-walls.sh`): `git clone --depth 1 https://github.com/dharmx/walls ~/Pictures/walls` (or `git pull` if present). Report the size with `du -sh` after the first clone.
- Exclude `animated/` (the `.mp4` files) from rotation. Xfce has no native video wallpapers, and video playback would keep the GPU busy and skew test results.
- `rice/wallsets.conf` defines named sets. **personal** = all categories (minus any Tete excludes). **client** = calm, neutral categories only (e.g. `nature`, `mountain`, `minimal`, `calm`, `aerial`, `fogsmoke`, `paper`) for use on other people's PCs.

**Dynamic theme engine: one command, `chiron rice apply <image>`**
1. Set the wallpaper on every monitor and workspace (Xfce backdrop properties via `xfconf-query`; detect the monitor names, don't hard-code them).
2. Run `wallust run <image>` with `check_contrast = true`.
3. wallust templates regenerate:
   - **GTK3/GTK4 colors:** a base theme that supports color overrides (e.g. adw-gtk3) plus `~/.config/gtk-3.0/gtk.css` and `~/.config/gtk-4.0/gtk.css` with `@define-color` values. Then force a reload (briefly switch `xsettings /Net/ThemeName` and back).
   - **xfwm4 window borders:** a theme that takes its colors from GTK, or a generated one.
   - **xfce4-panel:** GTK CSS for the panel.
   - **xfce4-terminal palette:** via xfconf.
   - **rofi** launcher theme, **xfce4-notifyd** styling, **btop** theme, **fastfetch** colors, **conky** colors, **starship** prompt colors.
   - **Papirus folder color:** pick the nearest available accent with `papirus-folders`. Install Papirus per-user (`~/.local/share/icons`) so this never needs root.
4. Total time under ~3 s. If something fails, keep the previous theme rather than leaving the desktop half-themed.

**Wallpaper switching**
- `Super+W` → `chiron rice pick`: rofi picker with thumbnails (thumbnails cached once).
- `Super+Shift+W` → `chiron rice random`: random wallpaper from the active set.
- Optional timed rotation (systemd user timer, interval asked from Tete).
- `chiron rice mode client|personal`: switches the wallpaper set (client mode also skips personal widgets).
- `chiron rice pause` / `chiron rice resume`: stop rotation and the compositor during tests. `chiron stress`/`full` call these automatically.

**Personalization layer**
- Fonts: a Nerd Font for the terminal (e.g. JetBrains Mono Nerd Font) and a UI font with **proper Thai support** (e.g. Noto Sans + Noto Sans Thai), since reports are Thai + English.
- Icons: Papirus. Cursor: Tete's pick.
- **Conky** widget showing live system stats in palette colors (fits a doctor drive).
- **fastfetch** with a custom "Chiron" ASCII logo in the terminal.
- **Static branding:** GRUB theme, Plymouth boot splash and LUKS unlock screen, and LightDM/slick-greeter login background (current wallpaper if feasible without running root on every change; otherwise a fixed image).
- Panel layout, dock (e.g. Plank), hotkeys: ask Tete.

**Performance and compatibility guards**
- Default terminal stays **xfce4-terminal**: GPU terminals like kitty/alacritty need OpenGL and can fail on old GPUs and in VMs. A GPU terminal is optional, with automatic fallback.
- Compositor: xfwm4's built-in one with light shadows only. No heavy blur by default. Auto-disable it when running on software rendering (llvmpipe) or in a VM.
- Idle RAM target for the riced desktop: roughly under 1 GB. Measure and report it.

**Done when:** `chiron rice apply` works on several very different wallpapers (dark, bright, low-color) with readable text every time · client/personal modes work · `chiron rice pause`/`resume` verified · desktop still boots and stays usable on software rendering in the VM · idle RAM measured · everything committed and pushed (section 5b) · snapshot `riced`.

### Phase 5 — The `chiron` tool (Tete + Claude Code)
Develop in a git repo in this folder (`./chiron/`). Deploy to `/opt/chiron` on the drive with rsync over SSH, with a wrapper at `/usr/local/bin/chiron`.

**Commands**
- `chiron report`: read-only health check, under ~3 minutes
- `chiron stress [--minutes 10]`: load tests with live safety limits
- `chiron full`: report + stress + combined verdict
- `chiron mount-ro <device>`: read-only mount helper (NTFS via ntfs3/ntfs-3g `ro`; BitLocker via `cryptsetup open --type bitlk --readonly` with a recovery key the owner types, `dislocker -r` as fallback). Refuses read-write.
- `chiron compare`: compare this machine with its previous report (also shown automatically when a previous report exists)
- `chiron forget <machine>`: delete all stored reports and history for one machine (when the owner asks)
- `chiron rice …` and `chiron walls update`: the desktop commands from Phase 4R
- `chiron help`: list every command (the README has the same table)

**Output:** `~/reports/YYYY-MM-DD_HHMM_<vendor>-<model>/` containing `report.md`, `report.html`, `report.json`, `owner-summary.html` and `raw/` (raw tool outputs). Never copy the owner's personal files.

**v1 feature 1 — Owner summary (Thai + English).** A one-page, printable `owner-summary.html` written for a non-technical owner. One line per area with a fixed-color verdict, plain-language meaning and a recommended action. Example: "Battery holds 58% of its original charge: expect about 2 hours away from the charger. Replacement recommended." / "แบตเตอรี่เก็บไฟได้ 58% ของตอนใหม่ …". Keep all wording in a message catalog (`chiron/i18n/en.json`, `th.json`); Tete reviews the Thai. Renders with the Thai-capable fonts from Phase 4R.

**v1 feature 2 — Windows 11 readiness + firmware info.**
- TPM present and version (`/sys/class/tpm/tpm0/tpm_version_major`), Secure Boot state, UEFI vs legacy boot (`/sys/firmware/efi`).
- Secure Boot certificates: which Microsoft CAs the firmware trusts (`mokutil --db`: UEFI CA 2011, UEFI CA 2023, Windows UEFI CA 2023). If they're out of date, say so in plain words.
- CPU model checked against a bundled copy of Microsoft's supported-CPU lists (store the source and date; note that the list is Microsoft's official rule).
- RAM ≥ 4 GB, storage ≥ 64 GB.
- BIOS vendor/version/date (`dmidecode -t bios`). If online, `fwupdmgr get-updates` read-only: report "firmware update available", never install.
- Output: "Ready / Not ready (reason) / Unknown".

**v1 feature 3 — Disk-full check.**
- Find OS partitions (NTFS containing `Windows/`, Linux roots). Mount them **read-only** with `chiron mount-ro`. ntfs-3g `ro` works on hibernated/Fast Startup volumes; never remove hibernation files.
- Report used/free space. Optionally show the largest top-level folders, time-capped.
- Thresholds: free < 10% or < 10 GB → 🔴, 10–20% → 🟡.
- BitLocker without an owner-provided key → "Encrypted: usage unknown", not an error.

**v1 feature 4 — "Not supported" vs "broken".**
For each PCI/USB device, check the kernel driver in use (`lspci -k`, `lsusb -t`) and missing-firmware messages in the kernel log. Classify each device as:
- **Works**
- **No Linux driver on this drive** (not a hardware fault)
- **Driver loaded but errors** (possible hardware fault)

Add cheap functional checks: Wi-Fi interface present and a scan works, Bluetooth controller present, webcam device present, audio card present. Never report a device as broken just because this drive can't drive it.

**v1 feature 5 — Before/after comparison.**
- Machine fingerprint = SHA-256 of (system UUID + board serial + product name + a per-drive random salt). No raw serials in folder names.
- History at `~/reports/history/<fingerprint>/`. If a previous report exists, show a delta table: battery health, max CPU temp, throttling %, disk speed, free space, SMART counters. Example: "CPU max temp 96 °C → 78 °C".

**Checks and starting thresholds** (heuristics; tune with real machines and explain each in code comments):

| Area | Source | 🟢 Green | 🟡 Yellow | 🔴 Red |
|---|---|---|---|---|
| Battery health | `/sys/class/power_supply/BAT*` full vs design (energy_* or charge_*) | ≥ 80% | 60–79% | < 60% or not charging |
| Battery cycles | `cycle_count` (if reported) | < 500 | 500–1000 | > 1000 |
| NVMe | `smartctl` / `nvme smart-log` | critical_warning 0, used < 80%, media errors 0 | used 80–100% | critical_warning ≠ 0, used > 100%, media errors > 0 |
| SATA SSD / HDD | SMART | PASSED, realloc 0, pending 0 | realloc 1–10, CRC errors | FAILED, pending > 0, uncorrectable > 0, realloc > 10 |
| Drive temperature | SMART | < 55 °C | 55–70 °C | > 70 °C |
| CPU under load | sensors / turbostat during stress, vs the CPU's own limit (Tjmax) | ≥ 10 °C below Tjmax, clocks steady | at Tjmax, or clock drop 10–25% | clock drop > 25%, or above Tjmax |
| RAM | `memtester` quick pass + EDAC/MCE in kernel log | pass | — | any error |
| Storage speed | `fio` sequential read, `--readonly` | ≥ 70% of class | 40–70% | < 40% |
| Kernel log | `journalctl -k`: I/O errors, MCE, ACPI, PCIe AER | none | warnings | errors |
| Fans | sensors (if exposed) | spinning under load | not reported | 0 rpm under load |
| GPU | `glmark2` short run | completes | low score for its class | crash / hang |
| Disk space (owner OS) | read-only mount | ≥ 20% free | 10–20% free | < 10% or < 10 GB free |
| Windows 11 readiness | TPM, Secure Boot, CPU list, RAM, storage | ready | unknown | not ready (with reason) |
| Device support | `lspci -k`, `lsusb`, kernel log | all work | no Linux driver on this drive | driver errors |

Speed classes (sequential read): NVMe ≥ 1500 MB/s · SATA SSD ≥ 450 MB/s · HDD ≥ 100 MB/s.

CPU temperatures are graded against each CPU's own limit (Tjmax: coretemp `temp*_crit`; AMD from a table). Many healthy thin laptops sit at Tjmax under full load by design; that alone is not red.

**Battery runtime estimate:** on battery at idle for ~5 minutes, measure power draw (W). Estimated runtime = `energy_now / power_now` (or `charge_now / current_now` when the battery reports charge instead of energy). Compare with the same draw on a new battery (`energy_full_design`).

**Stress safety:** abort if any CPU sensor stays above its own limit (Tjmax, or 97 °C when unknown) for more than 10 s, if running on battery below 25%, or on Ctrl-C. Always clean up (kill stress processes) on exit.

**Clean test conditions:** `stress`/`full` call `chiron rice pause` before testing and `chiron rice resume` afterwards, even after an abort or error.

**Read-only guarantees:** benchmarks on owner disks are read-only (`fio --readonly`). Never write test files to owner disks. Never mount read-write.

**Implementation notes:** Python 3 standard library (`subprocess`, `json`, `pathlib`). Each check is its own module returning `{status, summary, evidence}`. Missing hardware or tools gives "n/a", not a crash (VMs and desktops have no battery).

**Done when:** `chiron report` produces all report files in the VM (with "n/a" where hardware is absent), then on Tete's laptop with real hardware.

### Phase 6 — RAM test from the boot menu
- Download **PassMark MemTest86 Free** (Secure Boot–signed; the open-source MemTest86+ is not signed). Verify the download. Check and record its license terms in `PROGRESS.md`. Never commit the binaries: `setup/` downloads them.
- Copy its EFI files to the drive's ESP (e.g. `/boot/efi/EFI/memtest86/`), add a chainload entry in `/etc/grub.d/40_custom`, run `update-grub`.
- Verify it launches in the VM **with Secure Boot on**. If shim/GRUB refuses to chainload it, document that and rely on `memtester` in `chiron`.

**Done when:** the GRUB menu shows "MemTest86 (RAM test)" and it boots with Secure Boot on, or the fallback is documented.

### Phase 7 — Real-hardware tests (Tete boots, Claude Code guides)
Record each test in `PROGRESS.md`: Secure Boot state, boot OK, `lsusb -t` speed, Wi-Fi, `chiron report` OK, `chiron stress` OK, no-trace checks.

1. **Tete's own laptop** (details in `CLAUDE.local.md`). Some brands (e.g. Acer) need "F12 Boot Menu" enabled in the BIOS first. Compare `efibootmgr -v` before and after: no new entries.
2. **Tete's desktop (Windows).** Before: note the time, `manage-bde -status`, and `bcdedit /enum firmware` (admin). After returning to Windows: clock correct, no BitLocker recovery prompt, no new firmware boot entries.
3. **A consenting friend's or family member's PC**, only after tests 1 and 2 pass.
4. Optional: an old legacy-BIOS PC.

**Done when:** the table is filled in and every no-trace check passes.

### Phase 8 — Clean-up and hand-off
- Remove the temporary sudoers file, disable and remove `openssh-server`, delete setup SSH keys
- Clear shell history if it contains anything sensitive
- Final Timeshift snapshot `v1-release`
- Finalize `docs/USAGE.md`: how to boot (boot-menu keys by brand, and "Boot from file" for PCs that trust only the 2023 CA), how to run `chiron`, the consent checklist below
- Final README pass (screenshots of the rice and a sample owner summary with fake data), tag `v1.0.0`

**Done when:** the "Temporary — remove before done" list in `PROGRESS.md` is empty.

### Later (not v1)
- Windows PE partition (e.g. Hiren's BootCD PE) in the reserved ~13 GB, chainloaded from GRUB, for Windows-side repairs
- Move to Mint 23 (expected Dec 2026): in-place upgrade or reinstall with this plan (new installer); revisit the pinned-shim decision then
- Thai UI/input, nicer HTML report, longer battery test
- Separate project: Raspberry Pi NAS with the two 2.5" SSDs

---

## 7. Consent checklist (every machine)
- [ ] Owner agreed to: booting from USB and a read-only health check
- [ ] Owner agreed to the stress test (up to ~10 min) and knows a weak machine may shut down under load
- [ ] Laptop plugged into power for the stress test
- [ ] Owner types any BitLocker key or password themselves
- [ ] Owner's files are only read if they asked; nothing is copied unless they asked
- [ ] Report shown to the owner; delete it from the drive if they want

---

## 8. Open questions for Tete
- Thai input on the drive?
- Report language: owner summary is Thai + English (decided); technical report English only, or both?
- Rice: favorite and excluded wallpaper categories? Always dark, or follow each wallpaper? Rotation interval? Panel layout (top bar / bottom / dock)? Fonts and cursor? Hotkeys?
- Keep reports on the drive, or delete them after giving the owner a copy?

---

## 9. `PROGRESS.md` template (Claude Code creates it in Phase 0)

```markdown
# Chiron Stick — Progress

## Current phase
Phase 0

## Target drive
by-id path: …
SMART summary: …

## Temporary — remove before done
- (none yet)

## Log
| Date | Phase | Change | Verified by |
|---|---|---|---|
```

---

## 10. Prompts (paste into Claude Code)

### 10a. Starter prompt (first session)
```
Read CLAUDE.md fully. You are my setup engineer for Chiron Stick, and
this is an open-source project that gets published to GitHub as we build it.

1. Summarize the goal, scope, safety rules, and the GitHub publish workflow
   (section 5b) in your own words (short).
2. Before we start, tell me anything in CLAUDE.md that looks wrong, outdated
   (check current versions and package names), or risky.
3. Then do Phase 0 only, using read-only commands. Create PROGRESS.md and show
   me the evidence for each "Done when" item.

Stop after Phase 0 and wait for me. Never run a destructive command without
showing it to me first and getting my "yes".
```

### 10b. Rice kickoff prompt (when we reach Phase 4R)
```
We're starting Phase 4R, the desktop rice. I lead the look, you build it.

1. Ask me the rice questions from section 8 first (categories, dark or
   follow-the-wallpaper, rotation, panel layout, fonts, hotkeys).
2. Then propose 2–3 overall looks (describe each: panel, colors behavior,
   fonts, widgets). I'll pick one.
3. Build chiron rice apply first and test it on at least five very different
   wallpapers, showing me screenshots. Readable text every time.
4. Then the switcher, client/personal modes, chiron rice pause/resume, and the
   static branding (GRUB, Plymouth, login screen).

Follow the rice principles in section 4 and the guards in Phase 4R. Commit
and push each working piece following section 5b. Ask before big visual
choices.
```

### 10c. Every new session
```
Read CLAUDE.md and PROGRESS.md. Tell me where we are and what's next, then
wait. Remember: commit + push every finished feature or command (section 5b).
```
