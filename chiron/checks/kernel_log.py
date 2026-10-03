"""Hardware errors the kernel logged since this boot: disk I/O, machine checks, PCIe AER,
thermal throttling, GPU hangs. Lines about the stick's own disk are left out."""
import re

from chiron.model import Result, Status, worst
from chiron.util import sh

# (category, status, pattern). ACPI BIOS errors are very common firmware bugs, not hardware faults.
PATTERNS = [
    ("disk I/O errors", Status.RED, r"I/O error, dev \w+|Buffer I/O error on dev|critical (medium|target) error|medium error"),
    ("NVMe controller problems", Status.RED, r"nvme\d+.*(timeout|controller is down|Device not ready|resetting controller)"),
    ("machine check (CPU/RAM) errors", Status.RED, r"\[Hardware Error\]|Machine check events logged|mce: .*error"),
    ("PCIe errors (uncorrected)", Status.RED, r"AER: (Uncorrected|Multiple Uncorrected)"),
    ("GPU hangs", Status.RED, r"GPU HANG|gpu hang|ring \w+ timeout|\*ERROR\*.*(hang|timed out)|fifo: (read|write) fault"),
    ("SATA link problems", Status.YELLOW, r"ata\d+(\.\d+)?: (exception Emask|failed command|hard resetting link|SError:)"),
    ("PCIe errors (corrected)", Status.YELLOW, r"AER: (Corrected|Multiple Corrected)"),
    ("thermal throttling", Status.YELLOW, r"temperature above threshold|cpu clock throttled"),
    ("USB device problems", Status.YELLOW, r"usb \S+: (device descriptor read/\d+, error|device not accepting address|unable to enumerate)"),
    ("firmware (ACPI) bugs", Status.INFO, r"ACPI (BIOS )?Error|ACPI Exception"),
]


def kernel_log():
    rc, out, _ = sh(["journalctl", "-k", "-b", "--no-pager", "-o", "short-monotonic"], timeout=60)
    if rc != 0 or not out.strip():
        rc, out, _ = sh(["dmesg", "--color=never"])
    return out if rc == 0 else ""


def scan(log, own_disks=()):
    """{category: {"status", "count", "examples"}} for every pattern that matched."""
    own = re.compile(r"\b(" + "|".join(map(re.escape, own_disks)) + r")\d*\b") if own_disks else None
    found = {}
    for line in log.splitlines():
        if own and own.search(line):
            continue
        for cat, status, pat in PATTERNS:
            if re.search(pat, line):
                f = found.setdefault(cat, {"status": status, "count": 0, "examples": []})
                f["count"] += 1
                if len(f["examples"]) < 5:
                    f["examples"].append(line.strip()[:240])
                break
    return found


def run(ctx):
    log = kernel_log()
    if not log:
        return [Result("kernel_log", "Kernel log", Status.NA, "Couldn't read the kernel log (needs root).")]
    ctx.save_raw("kernel-log.txt", log)
    found = scan(log, sorted(ctx.own))
    if not found:
        return [Result("kernel_log", "Kernel log", Status.GREEN, "No hardware errors logged since boot.",
                       {}, ("kernel_log.green", {}))]
    status = worst([f["status"] for f in found.values()] or [Status.GREEN])
    if status == Status.INFO:
        status = Status.GREEN  # only harmless firmware noise
    summary = "; ".join(f"{f['count']}× {cat}" for cat, f in found.items())
    return [Result("kernel_log", "Kernel log", status, summary,
                   {cat: {"count": f["count"], "examples": f["examples"]} for cat, f in found.items()},
                   (f"kernel_log.{status.value}", {"what": ", ".join(c for c, f in found.items() if f["status"] == status)}))]
