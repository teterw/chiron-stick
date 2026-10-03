"""Read-only access to the PC's partitions. Every mount is read-only twice over: the partition is
set read-only in the kernel first (blockdev --setro, so the block layer refuses any write), then
mounted with options that are read-only *and* skip journal replay (a plain "ro" mount of ext4,
XFS or btrfs can still write while replaying a journal). Nothing is ever mounted read-write."""
import json
import re
from pathlib import Path

from chiron.util import own_disks, sh

MNT_ROOT = Path("/run/chiron/mnt")
STATE = Path("/run/chiron/mounts.json")
SAFE = "nodev,nosuid,noexec"
MOUNT_OPTS = {
    "ext4": f"ro,noload,{SAFE}", "ext3": f"ro,noload,{SAFE}", "ext2": f"ro,{SAFE}",
    "btrfs": f"ro,rescue=nologreplay,{SAFE}", "xfs": f"ro,norecovery,{SAFE}",
    "vfat": f"ro,{SAFE}", "exfat": f"ro,{SAFE}",
}


class MountError(Exception):
    pass


def fstype(dev):
    rc, out, _ = sh(["blkid", "-o", "value", "-s", "TYPE", dev])
    return out.strip() if rc == 0 else ""


def _state():
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {}


def _save(state):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=1))


def _check_not_own(dev):
    name = Path(dev).resolve().name
    from chiron.util import base_disks
    if base_disks(name) & own_disks():
        raise MountError(f"{dev} is on this stick's own disk")


def _setro(dev):
    """Make the block device read-only; returns True if we changed it (so we can restore it)."""
    rc, out, _ = sh(["blockdev", "--getro", dev])
    if rc == 0 and out.strip() == "1":
        return False
    rc, _, err = sh(["blockdev", "--setro", dev])
    if rc != 0:
        raise MountError(f"couldn't make {dev} read-only: {err.strip()}")
    return True


def mount_ro(dev, key=None):
    """Mount dev read-only under /run/chiron/mnt/<name>. BitLocker needs the owner's recovery key
    (opened with cryptsetup --readonly). Returns the mountpoint."""
    if not re.match(r"^/dev/[\w/.-]+$", dev):
        raise MountError(f"not a device path: {dev}")
    _check_not_own(dev)
    fs = fstype(dev)
    state = _state()
    for mp, s in state.items():
        if s["dev"] == dev:
            return mp
    setro = _setro(dev)
    mapper = None
    target = dev
    try:
        if fs == "BitLocker":
            if not key:
                raise MountError("BitLocker volume: needs the owner's recovery key")
            mapper = f"chiron-{Path(dev).name}"
            rc, _, err = sh(["cryptsetup", "open", "--type", "bitlk", "--readonly", "--key-file=-",
                              dev, mapper], input=key, timeout=120)
            if rc != 0:
                raise MountError(f"couldn't unlock BitLocker: {err.strip() or 'wrong key?'}")
            target = f"/dev/mapper/{mapper}"
            fs = fstype(target)
        elif fs == "crypto_LUKS":
            raise MountError("LUKS-encrypted volume: not supported by mount-ro")
        mp = MNT_ROOT / Path(dev).name
        mp.mkdir(parents=True, exist_ok=True)
        if fs == "ntfs":
            # ntfs-3g in read-only mode never writes, and works on hibernated/Fast Startup volumes
            cmd = ["ntfs-3g", "-o", f"ro,{SAFE}", target, str(mp)]
        elif fs in MOUNT_OPTS:
            cmd = ["mount", "-t", fs, "-o", MOUNT_OPTS[fs], target, str(mp)]
        else:
            raise MountError(f"unsupported or unknown filesystem: {fs or 'none'}")
        rc, _, err = sh(cmd, timeout=60)
        if rc != 0:
            raise MountError(f"mount failed: {err.strip()}")
    except Exception:
        if mapper:
            sh(["cryptsetup", "close", mapper])
        if setro:
            sh(["blockdev", "--setrw", dev])
        raise
    state[str(mp)] = {"dev": dev, "mapper": mapper, "setro": setro, "fstype": fs}
    _save(state)
    return str(mp)


def umount(mp):
    state = _state()
    s = state.pop(str(mp), None)
    rc, _, err = sh(["umount", str(mp)], timeout=60)
    if rc != 0 and "not mounted" not in err:
        raise MountError(f"couldn't unmount {mp}: {err.strip()}")
    if s:
        if s.get("mapper"):
            sh(["cryptsetup", "close", s["mapper"]])
        if s.get("setro"):
            sh(["blockdev", "--setrw", s["dev"]])
    try:
        Path(mp).rmdir()
    except OSError:
        pass
    _save(state)


def umount_all():
    for mp in list(_state()):
        try:
            umount(mp)
        except MountError:
            pass
