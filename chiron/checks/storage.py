"""Storage: SMART health of every internal/external disk (not the stick itself), drive
temperature, and a short read-only sequential read speed test."""
import json

from chiron.history import disk_id
from chiron.model import Result, Status, worst
from chiron.util import human_bytes, is_root, sh

# Sequential read speed a healthy drive of each class should reach (MB/s)
SPEED_CLASS = {"nvme": 1500, "ssd": 450, "hdd": 100}


def list_disks(own):
    rc, out, _ = sh(["lsblk", "-J", "-b", "-d", "-o", "NAME,TYPE,TRAN,SIZE,MODEL,SERIAL,ROTA,RM"])
    if rc != 0:
        return []
    disks = []
    for d in json.loads(out).get("blockdevices", []):
        name = d.get("name", "")
        if d.get("type") != "disk" or name in own or name.startswith(("zram", "loop", "sr", "ram")):
            continue
        if not d.get("size"):
            continue  # empty card reader slots
        disks.append(d)
    return disks


def smart_types():
    """{"/dev/sdb": "sat", ...} from smartctl --scan (USB bridges need -d sat etc.)."""
    rc, out, _ = sh(["smartctl", "--scan", "-j"])
    types = {}
    if rc in (0, 2) and out.strip():
        for d in json.loads(out).get("devices", []):
            types[d.get("name")] = d.get("type")
    return types


def ata_attr(smart, attr_id):
    for a in smart.get("ata_smart_attributes", {}).get("table", []):
        if a.get("id") == attr_id:
            return a.get("raw", {}).get("value")
    return None


def ata_endurance_used(smart):
    """'Percentage Used Endurance Indicator' from the ATA device statistics, if the SSD reports it."""
    for page in smart.get("ata_device_statistics", {}).get("pages", []):
        for e in page.get("table", []):
            if "Percentage Used Endurance" in e.get("name", ""):
                return e.get("value")
    return None


def drive_class(smart, disk):
    if smart.get("device", {}).get("protocol") == "NVMe" or disk["name"].startswith("nvme"):
        return "nvme"
    rot = smart.get("rotation_rate")
    if rot is None:
        rot = 1 if disk.get("rota") else 0
    return "hdd" if rot else "ssd"


def grade_temperature(temp):
    if temp is None:
        return Status.NA
    return Status.GREEN if temp < 55 else Status.YELLOW if temp <= 70 else Status.RED


def grade_smart(smart, cls):
    """SMART verdict and the counters behind it. Thresholds are heuristics (CLAUDE.md Phase 5)."""
    reasons, statuses, ev = [], [], {}
    passed = smart.get("smart_status", {}).get("passed")
    ev["smart_passed"] = passed
    if passed is False:
        statuses.append(Status.RED); reasons.append("SMART overall health FAILED")

    if cls == "nvme":
        log = smart.get("nvme_smart_health_information_log", {})
        for k in ("critical_warning", "percentage_used", "media_errors", "available_spare",
                  "available_spare_threshold", "power_on_hours", "unsafe_shutdowns", "num_err_log_entries"):
            if k in log:
                ev[k] = log[k]
        if log.get("critical_warning"):
            statuses.append(Status.RED); reasons.append(f"critical warning {log['critical_warning']}")
        used = log.get("percentage_used")
        if used is not None:
            if used > 100:
                statuses.append(Status.RED); reasons.append(f"rated endurance used up ({used}%)")
            elif used >= 80:
                statuses.append(Status.YELLOW); reasons.append(f"{used}% of rated endurance used")
        if log.get("media_errors"):
            statuses.append(Status.RED); reasons.append(f"{log['media_errors']} media errors")
        spare, thr = log.get("available_spare"), log.get("available_spare_threshold")
        if spare is not None and thr is not None and spare < thr:
            statuses.append(Status.RED); reasons.append(f"spare blocks low ({spare}%)")
    else:
        realloc, pending = ata_attr(smart, 5), ata_attr(smart, 197)
        offline_unc, reported_unc, crc = ata_attr(smart, 198), ata_attr(smart, 187), ata_attr(smart, 199)
        ev.update({"reallocated": realloc, "pending": pending, "offline_uncorrectable": offline_unc,
                   "reported_uncorrectable": reported_unc, "crc_errors": crc,
                   "power_on_hours": smart.get("power_on_time", {}).get("hours")})
        if pending:
            statuses.append(Status.RED); reasons.append(f"{pending} sectors waiting to be remapped")
        if offline_unc:
            statuses.append(Status.RED); reasons.append(f"{offline_unc} unreadable sectors")
        if realloc and realloc > 10:
            statuses.append(Status.RED); reasons.append(f"{realloc} reallocated sectors")
        elif realloc:
            statuses.append(Status.YELLOW); reasons.append(f"{realloc} reallocated sectors")
        if reported_unc:
            # Read errors reported in the past. On their own (no pending/unreadable sectors) they
            # can be old history, so yellow; a full surface test settles it.
            statuses.append(Status.YELLOW); reasons.append(f"{reported_unc} read errors reported in the past")
        if crc:
            statuses.append(Status.YELLOW); reasons.append(f"{crc} cable/connection (CRC) errors")
        used = ata_endurance_used(smart)
        if used is not None:
            ev["percentage_used"] = used
            if used >= 100:
                statuses.append(Status.RED); reasons.append(f"rated endurance used up ({used}%)")
            elif used >= 80:
                statuses.append(Status.YELLOW); reasons.append(f"{used}% of rated endurance used")
    if not statuses:
        statuses.append(Status.GREEN if passed else Status.NA)
    return worst(statuses), reasons, {k: v for k, v in ev.items() if v is not None}


def grade_speed(mbps, cls, tran):
    if mbps is None:
        return Status.NA
    if tran == "usb":
        return Status.INFO  # limited by the USB connection, not a drive fault
    ratio = mbps / SPEED_CLASS[cls]
    return Status.GREEN if ratio >= 0.7 else Status.YELLOW if ratio >= 0.4 else Status.RED


def read_speed(dev, seconds=8):
    """Sequential read speed in MB/s. fio --readonly: fio refuses to write anything."""
    rc, out, err = sh(["fio", "--name=seqread", f"--filename={dev}", "--readonly", "--rw=read",
                        "--bs=1M", "--direct=1", "--ioengine=libaio", "--iodepth=16",
                        f"--runtime={seconds}", "--time_based", "--output-format=json"],
                       timeout=seconds + 30)
    if rc != 0:
        return None, err.strip()[-200:]
    try:
        bw = json.loads(out[out.index("{"):])["jobs"][0]["read"]["bw_bytes"]
        return round(bw / 1_000_000), None
    except (ValueError, KeyError, IndexError):
        return None, "couldn't parse fio output"


def run(ctx):
    disks = list_disks(ctx.own)
    if not disks:
        return [Result("storage", "Storage", Status.NA, "No disks found (other than this stick).",
                       owner=("storage.none", {}))]
    if not is_root():
        return [Result("storage", "Storage", Status.NA, "Needs root to read SMART data.")]
    types = smart_types()
    results = []
    for d in disks:
        dev = f"/dev/{d['name']}"
        label = f"{(d.get('model') or 'Disk').strip()} ({human_bytes(d['size'])}, {d.get('tran') or 'internal'})"
        cmd = ["smartctl", "-j", "-x", dev]
        if types.get(dev) and types[dev] not in ("ata", "nvme", "scsi"):
            cmd[1:1] = ["-d", types[dev]]
        rc, out, _ = sh(cmd, timeout=60)
        ctx.save_raw(f"smartctl-{d['name']}.json", out)
        try:
            smart = json.loads(out)
        except ValueError:
            smart = {}
        cls = drive_class(smart, d)
        if not smart.get("smart_status") and not smart.get("nvme_smart_health_information_log"):
            status, reasons, ev = Status.NA, ["no SMART data (USB bridge or controller doesn't pass it on)"], {}
        else:
            status, reasons, ev = grade_smart(smart, cls)
        temp = smart.get("temperature", {}).get("current")
        st_temp = grade_temperature(temp)
        if st_temp in (Status.YELLOW, Status.RED):
            reasons.append(f"drive temperature {temp} °C")
        speed = err = None
        if not ctx.quick:
            speed, err = read_speed(dev)
        st_speed = grade_speed(speed, cls, d.get("tran"))
        if st_speed in (Status.YELLOW, Status.RED):
            reasons.append(f"slow reads: {speed} MB/s (expected ≥ {SPEED_CLASS[cls]} for this kind of drive)")
        overall = worst([status, st_temp, st_speed])
        summary = ", ".join(reasons) if reasons else "healthy"
        if speed:
            summary += f"; reads {speed} MB/s" + (" (over USB)" if d.get("tran") == "usb" else "")
        ev.update({"device": dev, "model": d.get("model"), "size_bytes": d["size"], "class": cls,
                   "transport": d.get("tran"), "temperature_c": temp, "read_mbps": speed, "speed_error": err,
                   # salted hash of the serial: matches the same drive across runs without storing the serial
                   "disk_id": disk_id(smart.get("serial_number") or d.get("serial") or dev)})
        results.append(Result("storage", label, overall, summary,
                              {k: v for k, v in ev.items() if v is not None},
                              (f"storage.{overall.value}" if overall != Status.NA else "storage.unknown",
                               {"model": (d.get("model") or "").strip(), "size": human_bytes(d["size"])})))
    return results
