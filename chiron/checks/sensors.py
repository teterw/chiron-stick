"""Temperature and fan sensors from /sys/class/hwmon (no sensors-detect: auto-loaded drivers only)."""
import re
from pathlib import Path

from chiron.model import Result, Status
from chiron.util import read, read_int

HWMON = Path("/sys/class/hwmon")
CPU_DRIVERS = ("coretemp", "k10temp", "zenpower", "cpu_thermal")


def readings():
    """[{chip, label, temp_c, crit_c}] and [{chip, label, rpm}] for every sensor."""
    temps, fans = [], []
    for h in sorted(HWMON.glob("hwmon*")):
        chip = read(h / "name") or h.name
        for t in sorted(h.glob("temp*_input")):
            n = re.match(r"temp(\d+)_input", t.name).group(1)
            v = read_int(t)
            if v is None:
                continue
            crit = read_int(h / f"temp{n}_crit") or read_int(h / f"temp{n}_max")
            temps.append({"chip": chip, "label": read(h / f"temp{n}_label") or f"temp{n}",
                          "temp_c": round(v / 1000, 1), "crit_c": round(crit / 1000) if crit else None})
        for f in sorted(h.glob("fan*_input")):
            n = re.match(r"fan(\d+)_input", f.name).group(1)
            fans.append({"chip": chip, "label": read(h / f"fan{n}_label") or f"fan{n}", "rpm": read_int(f)})
    return temps, fans


def cpu_temp(temps):
    """The CPU package temperature (or the hottest CPU sensor) and the CPU's own limit (Tjmax)."""
    cpu = [t for t in temps if t["chip"] in CPU_DRIVERS]
    if not cpu:
        return None, None
    pkg = [t for t in cpu if re.match(r"(Package id \d+|Tctl|Tdie)", t["label"])]
    pick = max(pkg or cpu, key=lambda t: t["temp_c"])
    crits = [t["crit_c"] for t in cpu if t["crit_c"]]
    return pick["temp_c"], (max(crits) if crits else None)


def run(ctx):
    temps, fans = readings()
    if not temps and not fans:
        return [Result("sensors", "Sensors", Status.NA, "No temperature or fan sensors exposed (normal in a VM).")]
    hot = [t for t in temps if t["crit_c"] and t["temp_c"] >= t["crit_c"]]
    status = Status.RED if hot else Status.INFO
    parts = [f"{len(temps)} temperature sensors, {len(fans)} fans"]
    if hot:
        parts.append("at or above their limit at idle: " + ", ".join(f"{t['chip']} {t['label']} {t['temp_c']} °C" for t in hot))
    spinning = [f for f in fans if f["rpm"]]
    if fans:
        parts.append(f"{len(spinning)} of {len(fans)} fans spinning at idle")
    return [Result("sensors", "Sensors", status, "; ".join(parts), {"temperatures": temps, "fans": fans})]
