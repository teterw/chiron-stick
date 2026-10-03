"""Per-machine history (CLAUDE.md feature 5). A salted fingerprint identifies a machine without
putting serial numbers anywhere visible; each run's key numbers are kept so the next run can show
what changed ("CPU max temp 96 °C -> 78 °C"). `chiron forget` removes a machine completely."""
import hashlib
import json
import os
import secrets
import shutil
from pathlib import Path

SALT = Path("/var/lib/chiron/salt")


def salt():
    """Random per-stick salt (root-only), so fingerprints mean nothing outside this stick."""
    try:
        return SALT.read_text().strip()
    except OSError:
        SALT.parent.mkdir(parents=True, exist_ok=True)
        s = secrets.token_hex(16)
        SALT.write_text(s + "\n")
        os.chmod(SALT, 0o600)
        return s


def _hash(*parts):
    return hashlib.sha256("|".join([salt(), *parts]).encode()).hexdigest()


def fingerprint(ident):
    """SHA-256 of system UUID + board serial + product name + the stick's salt (16 hex chars)."""
    return _hash(ident.get("product_uuid") or "", ident.get("board_serial") or "", ident.get("product_name") or "")[:16]


def disk_id(serial):
    return _hash("disk", serial or "")[:10]


def metrics(results):
    """The numbers worth comparing between runs, as {name: value}."""
    m = {}
    for r in results:
        e, area, title = r["evidence"], r["area"], r["title"]
        if area == "battery" and e.get("health_pct") is not None:
            m[f"{title}: health %"] = e["health_pct"]
            if e.get("cycles"):
                m[f"{title}: cycles"] = e["cycles"]
        elif area == "storage" and e.get("disk_id"):
            name = f"{(e.get('model') or 'disk').strip()} [{e['disk_id'][:4]}]"
            for k, label in (("read_mbps", "read MB/s"), ("temperature_c", "temp °C"), ("reallocated", "reallocated"),
                             ("pending", "pending"), ("media_errors", "media errors"), ("percentage_used", "wear %")):
                if e.get(k) is not None:
                    m[f"{name}: {label}"] = e[k]
        elif area == "diskspace" and e.get("free_bytes") is not None:
            m[f"{e.get('os', 'OS')}: free GB"] = round(e["free_bytes"] / 1e9, 1)
        elif area == "cpu" and e.get("idle_temp_c") is not None:
            m["CPU idle °C"] = e["idle_temp_c"]
        elif area == "cpu_load":
            for k, label in (("max_temp_c", "CPU max °C under load"), ("clock_drop_pct", "CPU clock drop %"),
                             ("throttle_events", "throttle events")):
                if e.get(k) is not None:
                    m[label] = e[k]
    return m


def compare(before, after):
    """Rows for every measurement taken in both runs that changed (a measurement only one run
    took, e.g. stress results after a report-only run, isn't a change)."""
    return [{"name": name, "before": before[name], "after": after[name]}
            for name in sorted(after) if name in before and before[name] != after[name]]


def _runs_file(root, fp):
    return root / "history" / fp / "runs.json"


def previous(root, fp):
    try:
        runs = json.loads(_runs_file(root, fp).read_text())
        return runs[-1] if runs else None
    except (OSError, ValueError):
        return None


def record(root, fp, created, report_folder, results):
    f = _runs_file(root, fp)
    f.parent.mkdir(parents=True, exist_ok=True)
    try:
        runs = json.loads(f.read_text())
    except (OSError, ValueError):
        runs = []
    runs.append({"created": created, "report": report_folder, "metrics": metrics(results)})
    f.write_text(json.dumps(runs, indent=1, ensure_ascii=False) + "\n")


def machines(root):
    """{fingerprint: [report folder names]} from every report.json under root."""
    out = {}
    for rj in sorted(root.glob("*/report.json")):
        try:
            fp = json.loads(rj.read_text()).get("fingerprint")
        except ValueError:
            continue
        if fp:
            out.setdefault(fp, []).append(rj.parent.name)
    return out


def forget(root, machine):
    """Delete every report and the history of one machine. `machine` is a fingerprint (or its
    first 6+ characters) or the name of one of its report folders. Returns what was deleted."""
    known = machines(root)
    fp = None
    for f, folders in known.items():
        if (len(machine) >= 6 and f.startswith(machine)) or machine in folders:
            fp = f
            break
    if not fp:
        return None
    deleted = []
    for folder in known[fp]:
        shutil.rmtree(root / folder, ignore_errors=True)
        deleted.append(folder)
    shutil.rmtree(root / "history" / fp, ignore_errors=True)
    return fp, deleted
