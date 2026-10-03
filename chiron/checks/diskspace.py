"""Disk space on the PC's own operating systems (CLAUDE.md feature 3): find Windows and Linux
system partitions, mount them read-only (chiron.mount), report used/free space."""
import json
import os
import re
from pathlib import Path

from chiron.model import Result, Status
from chiron.mount import MountError, mount_ro, umount
from chiron.util import human_bytes, is_root, read, sh

MIN_SIZE = 8 * 1000**3  # skip recovery/EFI/boot partitions


def grade_free(free, total):
    # Thresholds (CLAUDE.md Phase 5): Windows updates and swap need room; < 10% or < 10 GB hurts
    if not total:
        return Status.NA
    pct = 100 * free / total
    if pct < 10 or free < 10 * 1000**3:
        return Status.RED
    return Status.YELLOW if pct < 20 else Status.GREEN


def candidates(own):
    rc, out, _ = sh(["lsblk", "-J", "-b", "-o", "NAME,PATH,FSTYPE,SIZE,TYPE,PKNAME,LABEL"])
    found = []

    def walk(devs, disk=None):
        for d in devs:
            top = disk or d["name"]
            if d.get("type") in ("part", "disk") and top not in own and (d.get("size") or 0) >= MIN_SIZE \
                    and d.get("fstype") in ("ntfs", "ext4", "btrfs", "xfs", "BitLocker", "crypto_LUKS"):
                found.append(d)
            walk(d.get("children", []), top)
    if rc == 0:
        walk(json.loads(out).get("blockdevices", []))
    return found


def identify(mp):
    """What's on a mounted partition: ("Windows", ...), ("Linux", name) or ("data", None)."""
    if os.path.isdir(os.path.join(mp, "Windows", "System32")):
        return "Windows", None
    for root in ("", "@", "@rootfs", "root"):  # btrfs layouts keep the system in a subvolume
        rel = read(os.path.join(mp, root, "etc", "os-release"))
        if rel:
            m = re.search(r'^PRETTY_NAME="?([^"\n]+)', rel, re.M)
            return "Linux", (m.group(1) if m else "Linux")
    return "data", None


def run(ctx):
    if not is_root():
        return [Result("diskspace", "Disk space", Status.NA, "Needs root to mount partitions read-only.")]
    results = []
    for d in candidates(ctx.own):
        dev, fs = d["path"], d.get("fstype")
        if fs in ("BitLocker", "crypto_LUKS"):
            kind = "BitLocker" if fs == "BitLocker" else "LUKS"
            results.append(Result("diskspace", f"Disk space {dev}", Status.INFO,
                                  f"{human_bytes(d['size'])} {kind}-encrypted partition: usage unknown "
                                  f"(`chiron mount-ro {dev}` with the owner's recovery key)",
                                  {"device": dev, "encryption": kind}, ("diskspace.encrypted", {"kind": kind})))
            continue
        try:
            mp = mount_ro(dev)
        except MountError as e:
            results.append(Result("diskspace", f"Disk space {dev}", Status.NA, f"couldn't open read-only: {e}", {"device": dev}))
            continue
        try:
            os_kind, name = identify(mp)
            st = os.statvfs(mp)
            total, free = st.f_blocks * st.f_frsize, st.f_bavail * st.f_frsize
        finally:
            umount(mp)
        if os_kind == "data":
            continue  # only operating systems are graded; data partitions aren't "full" in the same way
        status = grade_free(free, total)
        label = name or os_kind
        pct = round(100 * free / total) if total else None
        results.append(Result("diskspace", f"Disk space: {label} ({dev})", status,
                              f"{label}: {human_bytes(free)} free of {human_bytes(total)} ({pct}%)",
                              {"device": dev, "os": label, "fstype": fs, "free_bytes": free, "total_bytes": total,
                               "free_pct": pct},
                              (f"diskspace.{status.value}", {"os": label, "free": human_bytes(free), "pct": pct})))
    if not results:
        results.append(Result("diskspace", "Disk space", Status.NA, "No Windows or Linux system found on the PC's disks.",
                              owner=("diskspace.none", {})))
    return results
