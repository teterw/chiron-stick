"""Battery: health (full vs design capacity), charge cycles, charging state, runtime estimate."""
from pathlib import Path

from chiron.model import Result, Status, worst
from chiron.util import read, read_int

PS = Path("/sys/class/power_supply")


def grade_health(pct):
    # Heuristic thresholds (CLAUDE.md Phase 5 table): most laptops ship with ~100% and lose
    # a few % per year; below 80% runtime loss becomes noticeable, below 60% it hurts.
    if pct is None:
        return Status.NA
    return Status.GREEN if pct >= 80 else Status.YELLOW if pct >= 60 else Status.RED


def grade_cycles(cycles):
    # Typical laptop cells are rated for roughly 300-1000 full cycles.
    if not cycles:  # 0 or missing usually means "not reported"
        return Status.NA
    return Status.GREEN if cycles < 500 else Status.YELLOW if cycles <= 1000 else Status.RED


def read_battery(path):
    """All values from one /sys/class/power_supply/BATx folder, in Wh/W (energy) or Ah/A (charge)."""
    def val(name):
        v = read_int(path / name)
        return None if v is None else v / 1_000_000

    energy = val("energy_full") is not None
    full = val("energy_full") if energy else val("charge_full")
    design = val("energy_full_design") if energy else val("charge_full_design")
    now = val("energy_now") if energy else val("charge_now")
    rate = val("power_now") if energy else val("current_now")
    return {
        "name": path.name,
        "manufacturer": read(path / "manufacturer"),
        "model": read(path / "model_name"),
        "technology": read(path / "technology"),
        "unit": "Wh" if energy else "Ah",
        "full": full, "design": design, "now": now,
        "rate": abs(rate) if rate else rate,  # some firmware reports negative current while discharging
        "status": read(path / "status"),
        "capacity_pct": read_int(path / "capacity"),
        "cycles": read_int(path / "cycle_count"),
    }


def ac_online():
    for p in PS.glob("*"):
        if read(p / "type") in ("Mains", "USB") and read_int(p / "online") == 1:
            return True
    return False


def evaluate(b, on_ac):
    """Grade one battery reading. Returns (status, summary, evidence, owner params)."""
    health = round(100 * b["full"] / b["design"], 1) if b["full"] and b["design"] else None
    statuses = [grade_health(health), grade_cycles(b["cycles"])]
    notes = []
    if b["status"] == "Not charging" and on_ac and (b["capacity_pct"] or 0) < 90:
        # Could be a charge-limit setting (e.g. "conservation mode") or a charging fault
        statuses.append(Status.YELLOW)
        notes.append("not charging while plugged in (charge limit setting, or a charging fault)")

    hours_now = hours_full = None
    if b["status"] == "Discharging" and b["rate"]:
        hours_now = round(b["now"] / b["rate"], 1) if b["now"] else None
        hours_full = round(b["full"] / b["rate"], 1) if b["full"] else None

    parts = [f"health {health:.0f}%" if health is not None else "health unknown"]
    if b["cycles"]:
        parts.append(f"{b['cycles']} cycles")
    parts.append(b["status"] or "status unknown")
    if hours_full:
        parts.append(f"~{hours_full} h on a full charge at the current load")
    parts += notes
    evidence = {k: v for k, v in b.items() if v not in (None, "")}
    evidence.update({"health_pct": health, "on_ac": on_ac, "hours_now": hours_now, "hours_full": hours_full})
    params = {"pct": round(health) if health is not None else None, "cycles": b["cycles"], "hours": hours_full}
    return worst(statuses), "; ".join(parts), evidence, params


def run(ctx):
    bats = [p for p in sorted(PS.glob("*"))
            if read(p / "type") == "Battery" and read(p / "scope") != "Device"]  # skip mice/keyboards
    if not bats:
        return [Result("battery", "Battery", Status.NA, "No battery (desktop or VM).",
                       owner=("battery.none", {}))]
    on_ac = ac_online()
    results = []
    for p in bats:
        b = read_battery(p)
        status, summary, evidence, params = evaluate(b, on_ac)
        key = f"battery.{status.value}" if status != Status.NA else "battery.unknown"
        if params["hours"] and status != Status.NA:
            key += ".h"  # variant that also tells the owner the expected runtime
        results.append(Result("battery", f"Battery {p.name}", status, summary, evidence, (key, params)))
    return results
