"""Windows 11 readiness and firmware info (CLAUDE.md feature 2): TPM 2.0, UEFI + Secure Boot,
CPU on Microsoft's list, RAM >= 4 GB, storage >= 64 GB. Plus BIOS version, whether a firmware
update is available (read-only, never installed), and which Microsoft Secure Boot certificates
the firmware trusts (the 2011 ones expired in 2026; see CLAUDE.md decision 3)."""
import json
import re
from pathlib import Path

from chiron import win11_cpu
from chiron.checks.cpu import cpu_model
from chiron.model import Result, Status
from chiron.util import meminfo, read, sh

CERTS = {"Microsoft Corporation UEFI CA 2011": "uefi2011", "Microsoft UEFI CA 2023": "uefi2023",
         "Windows UEFI CA 2023": "windows2023", "Microsoft Windows Production PCA 2011": "windows2011"}


def tpm_version():
    v = read("/sys/class/tpm/tpm0/tpm_version_major")
    return int(v) if v and v.isdigit() else None


def secure_boot_certs():
    """{"uefi2011": True, ...} from the firmware's db, or None if unreadable (legacy boot)."""
    rc, out, _ = sh(["mokutil", "--db"])
    if rc != 0:
        return None
    found = {v: False for v in CERTS.values()}
    for cn, key in CERTS.items():
        if re.search(r"CN=" + re.escape(cn) + r"\b", out):
            found[key] = True
    return found


def largest_internal_disk(own):
    rc, out, _ = sh(["lsblk", "-J", "-b", "-d", "-o", "NAME,TYPE,TRAN,SIZE"])
    if rc != 0:
        return None
    sizes = [d["size"] for d in json.loads(out).get("blockdevices", [])
             if d.get("type") == "disk" and d["name"] not in own and d.get("tran") != "usb"
             and not d["name"].startswith(("zram", "loop", "sr"))]
    return max(sizes, default=None)


def firmware_update():
    """Read-only check with fwupd. Returns a short text, or None when offline/unknown."""
    rc, out, _ = sh(["fwupdmgr", "get-updates", "--json", "--no-unreported-check", "--no-metadata-check"], timeout=45)
    if rc != 0 or not out.strip().startswith("{"):
        return None
    try:
        devs = json.loads(out).get("Devices", [])
    except ValueError:
        return None
    ups = [f"{d.get('Name')}: {d['Releases'][0].get('Version')}" for d in devs if d.get("Releases")]
    return "; ".join(ups) if ups else "none"


def evaluate(tpm, uefi, sb, cpu_ok, ram_gib, disk_bytes):
    """Ready / Not ready / Unknown with reasons."""
    fails, unknown = [], []
    if tpm is None:
        fails.append("no TPM 2.0 found (it may just be switched off in the firmware settings)")
    elif tpm < 2:
        fails.append(f"TPM {tpm}.x (needs 2.0)")
    if not uefi:
        unknown.append("booted in legacy mode, so UEFI/Secure Boot support can't be checked")
    if cpu_ok[0] is False:
        fails.append(f"CPU {cpu_ok[1]}")
    elif cpu_ok[0] is None:
        unknown.append(cpu_ok[1])
    if ram_gib < 3.8:  # 4 GB minus what firmware/graphics reserve
        fails.append(f"only {ram_gib} GiB RAM (needs 4 GB)")
    if disk_bytes is None:
        unknown.append("no internal disk found")
    elif disk_bytes < 64 * 1000**3:
        fails.append(f"disk only {disk_bytes / 1000**3:.0f} GB (needs 64 GB)")
    if fails:
        return Status.RED, "Not ready: " + "; ".join(fails), fails + unknown
    if unknown:
        return Status.YELLOW, "Unknown: " + "; ".join(unknown), unknown
    return Status.GREEN, "Ready for Windows 11", []


def run(ctx):
    uefi = Path("/sys/firmware/efi").exists()
    rc, out, _ = sh(["mokutil", "--sb-state"])
    sb = ("enabled" in out) if rc == 0 else None
    tpm = tpm_version()
    model = cpu_model()
    cpu_ok = win11_cpu.check(model)
    ram_gib = round(meminfo().get("MemTotal", 0) / 1024 / 1024, 1)
    disk = largest_internal_disk(ctx.own)
    status, summary, reasons = evaluate(tpm, uefi, sb, cpu_ok, ram_gib, disk)
    certs = secure_boot_certs() if uefi else None
    fw = firmware_update()
    ev = {"tpm_version": tpm, "uefi": uefi, "secure_boot": sb, "cpu": model, "cpu_check": cpu_ok[1],
          "ram_gib": ram_gib, "largest_disk_bytes": disk, "reasons": reasons, "secure_boot_certs": certs,
          "bios": {k: read(f"/sys/class/dmi/id/{k}") for k in ("bios_vendor", "bios_version", "bios_date")},
          "firmware_update": fw}
    results = [Result("win11", "Windows 11 readiness", status, summary, ev,
                      (f"win11.{status.value}", {"why": "; ".join(reasons)}))]
    if certs is not None:
        old_only = certs["uefi2011"] and not certs["uefi2023"]
        cert_status = Status.YELLOW if old_only else Status.GREEN if certs["uefi2023"] else Status.INFO
        results.append(Result("secureboot_certs", "Secure Boot certificates", cert_status,
                              "has the 2023 Microsoft certificates" if certs["uefi2023"]
                              else "only the 2011 Microsoft certificates (expired June 2026): a Windows or firmware update should add the 2023 ones",
                              certs, (f"sbcerts.{cert_status.value}", {})))
    if fw and fw != "none":
        results.append(Result("firmware", "Firmware update", Status.INFO, f"update available: {fw} (not installed)",
                              {"available": fw}, ("firmware.update", {})))
    return results
