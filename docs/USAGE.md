# Using Chiron Stick

## 1. Before you start: consent

Do these with the owner, every time:

- [ ] The owner agreed to booting from USB and a read-only health check
- [ ] The owner agreed to the stress test (up to ~10 minutes) and knows a weak machine may shut down under load
- [ ] Laptop plugged into power for the stress test
- [ ] The owner types any BitLocker key or password themselves
- [ ] The owner's files are only read if they asked; nothing is copied unless they asked
- [ ] Report shown to the owner; delete it from the stick if they want (`chiron forget`)

## 2. Boot from the stick

1. Shut the PC down completely. Plug the stick into a USB port (a blue or USB-C port is faster).
2. Power on and press the **boot menu key** right away:

   | Maker | Boot menu key |
   |---|---|
   | Acer | F12 (on some models enable "F12 Boot Menu" in the firmware settings first) |
   | ASUS | Esc (laptops), F8 (desktops) |
   | Dell | F12 |
   | HP | F9 (or Esc, then F9) |
   | Lenovo | F12 (or the small Novo button) |
   | MSI | F11 |
   | Gigabyte | F12 |
   | ASRock | F11 |
   | Toshiba / Dynabook | F12 |

3. Pick the entry for the stick (often "UEFI: <USB drive name>"). **Don't change any firmware settings**: changing them can trigger a BitLocker recovery prompt on the owner's Windows.
4. In the Chiron Stick menu, pick **Linux Mint** (or **MemTest86 (RAM test)** for a full memory test).
5. Type the stick's disk passphrase, then log in.

If the PC refuses to boot the stick with a Secure Boot error:
- Newer PCs that trust only Microsoft's 2023 certificate: in the boot menu choose **Boot from file** → the stick → `EFI/ubuntu/shimx64.efi`.
- Microsoft Surface and many Lenovo "Secured-core" PCs block third-party bootloaders by default. Changing that is a firmware setting, so skip these machines.

## 3. Check the PC

Open a terminal and run:

| Command | What it does |
|---|---|
| `chiron report` | Read-only health check, about 3 minutes |
| `chiron full` | Report + stress tests + one combined verdict (laptop on the charger) |
| `chiron stress --minutes 10` | Only the load tests. Ctrl-C stops them safely |
| `chiron compare` | What changed since this PC's last check |
| `chiron mount-ro /dev/sdXN` | Open one of the owner's partitions read-only. BitLocker: the owner types the recovery key |
| `chiron umount all` | Undo every `mount-ro` |
| `chiron forget <machine>` | Delete every report and the history of one PC |
| `chiron help` | All commands |

The commands ask for your password once (they need root to read the hardware). Results go to `~/reports/<date>_<maker>-<model>/`:

- **owner-summary.html**: one page in Thai and English for the owner. Print it or save it as PDF.
- **report.html** / **report.md**: the technical report.
- **report.json** and **raw/**: everything measured, for later comparison.

Green, yellow and red always mean the same thing and never take on the desktop theme's colours.

## 4. The desktop

The desktop takes its colours from the wallpaper: change the wallpaper and everything follows. **Super** is the Windows key.

| Keys or command | What it does |
|---|---|
| `Super+W` | Pick a wallpaper: type to filter, Enter to apply, Esc to cancel |
| `Super+Shift+W` | Random wallpaper |
| `Super+D` | Find and start an app |
| `Super+Return` | Terminal |
| `chiron rice mode client` | On someone else's PC: calm wallpapers, no automatic changes |
| `chiron rice mode personal` | The whole collection, a new wallpaper every 30 minutes |
| `chiron walls update` | Download or update the wallpaper collection (about 3 GB) |

The stress tests pause wallpaper changes and desktop effects by themselves (`chiron rice pause` and `chiron rice resume` do it by hand). On PCs without working graphics drivers, and in virtual machines, desktop effects stay off so the desktop stays quick.

## 5. Leave without a trace

1. Shut the stick down from the menu (don't just pull it out).
2. Unplug it once the PC is off.

The stick never adds firmware boot entries, never writes the PC's clock, never mounts its disks read-write, and doesn't run an SSH server.
