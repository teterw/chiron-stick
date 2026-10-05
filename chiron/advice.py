"""What to do about a finding (Tete, 2026-10-05: "What to do"): a short next step for whoever runs
the check and, when something needs replacing, the part to look for. The report lists them, the owner
summary adds the parts to its Thai/English advice, and the doctor shows them on each node."""


def nominal(size_bytes):
    """A drive's size as it's sold: 240 GB, 512 GB, 1 TB, 1.5 TB."""
    if size_bytes >= 999_000_000_000:
        tb = size_bytes / 1e12
        return f"{tb:.0f} TB" if abs(tb - round(tb)) < 0.06 else f"{tb:.1f} TB"
    return f"{round(size_bytes / 1e9)} GB"

GRADED = ("yellow", "red")


def _battery(r, red):
    ev = r["evidence"]
    bits = [" ".join(x for x in (ev.get("manufacturer"), ev.get("model")) if x)]
    if ev.get("technology"):
        bits.append(ev["technology"])
    if ev.get("design") and ev.get("unit") == "Wh":
        bits.append(f"{ev['design']:.0f} Wh")
    part = "Battery " + " · ".join(b for b in bits if b) if any(bits) else "A battery for this model"
    if red:
        return "Replace the battery: it no longer holds enough charge.", part
    return "The battery is wearing out: plan a replacement within a year or so.", part


def _storage(r, red):
    ev = r["evidence"]
    if ev.get("transport") == "usb":
        part = None  # an external drive, not part of the computer
    else:
        size = f", {nominal(ev['size_bytes'])} or larger" if ev.get("size_bytes") else ""
        part = {"nvme": f"M.2 NVMe SSD{size}",
                "ssd": f"SATA SSD{size} · 2.5-inch or M.2 SATA, like the old one",
                "hdd": f"SATA hard drive{size} · or a SATA SSD: much faster"}.get(ev.get("class"))
    if red:
        return "Back up the owner's files now, then replace the drive.", part
    if "MB/s" in r.get("summary", "") and "health" not in r.get("summary", "").lower():
        return "The drive reads slowly: check its cable or port; back up, it may be ageing.", part
    return "Back up important files and recheck the drive in a few months.", part


def _win11(r, red):
    reasons = " ".join(r["evidence"].get("reasons") or [r.get("summary", "")]).lower()
    steps = []
    if "tpm" in reasons:
        steps.append("turn on TPM (Intel PTT / AMD fTPM) in the firmware settings, if it has one")
    if "secure boot" in reasons:
        steps.append("turn on Secure Boot in the firmware settings")
    if "uefi" in reasons or "legacy" in reasons:
        steps.append("Windows has to be installed in UEFI mode (a disk conversion: only with a backup)")
    if "cpu" in reasons or "processor" in reasons:
        steps.append("the processor isn't on Microsoft's list: Windows 11 needs newer hardware")
    if "ram" in reasons or "memory" in reasons:
        steps.append("add RAM: Windows 11 needs 4 GB or more")
    if not steps:
        steps.append("see the report's details for what's missing")
    text = "; ".join(steps)
    return text[:1].upper() + text[1:] + ".", None


def _gpu(r, red):
    if red:
        return "The graphics test crashed or hung: check the cooling and the drivers in the owner's own system.", None
    return "No graphics acceleration on the stick: usually a missing driver here, not a fault.", None


ADVICE = {
    "battery": _battery,
    "storage": _storage,
    "win11": _win11,
    "diskspace": lambda r, red: ("Free up space: empty the Recycle Bin, remove programs nobody uses, and move photos "
                                 "and videos to an external drive.", None),
    "memory": lambda r, red: ("Memory errors: run MemTest86 from the stick's boot menu to find the faulty stick, "
                              "then replace it.", "A RAM stick of the same type and speed (see the spec sheet)"),
    "ram_test": lambda r, red: ("The memory test found errors: run MemTest86 from the boot menu for a full test, "
                                "then replace the faulty stick.", "A RAM stick of the same type and speed (see the spec sheet)"),
    "cpu": lambda r, red: ("The processor runs hot even at rest: clean the fan and vents with compressed air.", None),
    "cpu_load": lambda r, red: ("The processor overheats under load: clean the fan and vents with compressed air, "
                                "then renew the thermal paste if it still runs hot.",
                                "Thermal paste (and cleaning)" if red else None),
    "fans": lambda r, red: ("A fan doesn't spin under load: clean it, or replace it if it still doesn't turn.",
                            "A fan for this model" if red else None),
    "gpu": _gpu,
    "kernel_log": lambda r, red: ("The hardware error log has entries: read them in the full report to see which "
                                  "part is complaining.", None),
    "devices": lambda r, red: ("A built-in device reports driver errors: see the full report for which one.", None),
    "secureboot_certs": lambda r, red: ("Install the owner's Windows updates: they bring Microsoft's 2023 Secure Boot "
                                        "certificates.", None),
    "firmware": lambda r, red: ("A firmware (BIOS) update is available: get it from the maker's website.", None),
    "sensors": lambda r, red: ("A temperature is high at rest: check the cooling.", None),
}


def todo_for(result):
    """{"area", "title", "status", "action", "part"} for an amber or red finding, else None."""
    if result.get("status") not in GRADED:
        return None
    area = result.get("area", "").split(":")[0]
    fn = ADVICE.get(area)
    red = result["status"] == "red"
    result = {**result, "evidence": result.get("evidence") or {}}
    if fn:
        action, part = fn(result, red)
    else:
        action, part = "See the full report for details.", None
    return {"area": area, "title": result.get("title", area), "status": result["status"], "action": action, "part": part}


def todo(results):
    """The to-do list of a whole report: red first, then amber, in report order within each."""
    items = [t for t in (todo_for(r) for r in results) if t]
    return [t for t in items if t["status"] == "red"] + [t for t in items if t["status"] == "yellow"]
