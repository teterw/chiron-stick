"""Inventory: who made the machine, firmware, boot mode, virtualization. Facts only (INFO)."""
from pathlib import Path

from chiron.model import Result, Status
from chiron.util import read, sh

DMI = Path("/sys/class/dmi/id")


def identity():
    """Machine identity from DMI. Serial and UUID need root (they feed the history fingerprint)."""
    return {k: read(DMI / k) for k in ("sys_vendor", "product_name", "product_version", "product_family",
                                         "board_vendor", "board_name", "board_serial", "product_uuid",
                                         "bios_vendor", "bios_version", "bios_date", "chassis_type")}


CHASSIS = {"8": "portable", "9": "laptop", "10": "notebook", "14": "sub-notebook", "30": "tablet",
           "31": "convertible", "32": "detachable", "3": "desktop", "4": "desktop", "6": "mini tower",
           "7": "tower", "13": "all-in-one", "35": "mini PC"}


def boot_mode():
    if not Path("/sys/firmware/efi").exists():
        return "legacy BIOS", None
    rc, out, _ = sh(["mokutil", "--sb-state"])
    sb = "enabled" in out if rc == 0 else None
    return "UEFI", sb


def run(ctx):
    i = identity()
    mode, sb = boot_mode()
    rc, virt, _ = sh(["systemd-detect-virt"])
    virt = virt.strip() if rc == 0 else "none"
    kind = CHASSIS.get(i.get("chassis_type") or "", "computer")
    ev = {k: v for k, v in i.items() if v and k not in ("board_serial", "product_uuid")}
    ev.update({"kind": kind, "boot_mode": mode, "secure_boot": sb, "virtualization": virt})
    name = " ".join(x for x in (i.get("sys_vendor"), i.get("product_name")) if x) or "Unknown machine"
    summary = (f"{name} ({kind}); BIOS {i.get('bios_version') or '?'} ({i.get('bios_date') or '?'}); "
               f"booted in {mode} mode" + (f", Secure Boot {'on' if sb else 'off'}" if sb is not None else "")
               + (f"; running in a VM ({virt})" if virt != "none" else ""))
    return [Result("system", "System", Status.INFO, summary, ev)]
