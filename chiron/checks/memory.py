"""Memory: size, installed modules, and hardware-reported memory errors (EDAC).
The memtester pass runs in `chiron stress`; machine-check errors are in kernel_log."""
from pathlib import Path

from chiron.model import Result, Status
from chiron.util import is_root, meminfo, read_int, sh


def edac_counts():
    ce = ue = None
    for mc in Path("/sys/devices/system/edac/mc").glob("mc*"):
        c, u = read_int(mc / "ce_count"), read_int(mc / "ue_count")
        if c is not None:
            ce = (ce or 0) + c
        if u is not None:
            ue = (ue or 0) + u
    return ce, ue


def modules():
    """Installed memory modules from dmidecode type 17 (needs root)."""
    if not is_root():
        return []
    rc, out, _ = sh(["dmidecode", "-t", "17"])
    mods, cur = [], None
    for line in out.splitlines():
        if line.startswith("Memory Device"):
            cur = {}
            mods.append(cur)
        elif cur is not None and ":" in line:
            k, v = (x.strip() for x in line.split(":", 1))
            if k in ("Size", "Type", "Speed", "Configured Memory Speed", "Manufacturer", "Part Number", "Locator", "Form Factor"):
                cur[k] = v
    return [m for m in mods if m.get("Size") and "No Module" not in m["Size"]]


def run(ctx):
    total_gib = round(meminfo().get("MemTotal", 0) / 1024 / 1024, 1)
    ce, ue = edac_counts()
    mods = modules()
    ev = {"total_gib": total_gib, "modules": mods}
    if ce is not None:
        ev.update({"edac_corrected": ce, "edac_uncorrected": ue})
    if ue:
        status, summary = Status.RED, f"{ue} uncorrectable memory errors reported by the hardware"
    elif ce:
        status, summary = Status.YELLOW, f"{ce} corrected memory errors reported by the hardware"
    else:
        status = Status.GREEN if ce is not None else Status.INFO
        summary = f"{total_gib} GiB" + (f" in {len(mods)} module(s)" if mods else "") + \
                  ("; no hardware-reported errors" if ce is not None else "; RAM test runs in `chiron stress`")
    return [Result("memory", "Memory", status, summary, ev,
                   (f"memory.{status.value}" if status in (Status.YELLOW, Status.RED) else "memory.ok",
                    {"gib": total_gib}))]
