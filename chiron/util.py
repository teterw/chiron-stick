"""Small helpers: run commands safely, read sysfs files, find the stick's own disks."""
import os
import re
import shutil
import subprocess
from pathlib import Path


def sh(cmd, timeout=30, env=None, input=None):
    """Run a command (no shell). Never raises: returns (returncode, stdout, stderr).
    127 = tool not installed, 124 = timed out, 126 = couldn't start."""
    if not shutil.which(cmd[0]):
        return 127, "", f"{cmd[0]}: not installed"
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, errors="replace",
                           timeout=timeout, env=env, input=input)
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired as e:
        out = e.stdout.decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        return 124, out, f"{cmd[0]}: timed out after {timeout}s"
    except OSError as e:
        return 126, "", str(e)


def have(tool):
    return shutil.which(tool) is not None


def read(path, default=None):
    try:
        with open(path, errors="replace") as f:
            return f.read().strip()
    except OSError:
        return default


def read_int(path, default=None):
    try:
        return int(read(path))
    except (TypeError, ValueError):
        return default


def is_root():
    return os.geteuid() == 0


def meminfo():
    """/proc/meminfo as {key: kB}."""
    out = {}
    for line in (read("/proc/meminfo") or "").splitlines():
        m = re.match(r"(\w+):\s+(\d+)", line)
        if m:
            out[m.group(1)] = int(m.group(2))
    return out


def base_disks(devname):
    """Kernel names of the whole disks under a block device, following partitions and
    device-mapper layers (e.g. dm-0 -> sda4 -> sda)."""
    sysdir = Path("/sys/class/block") / devname
    if not sysdir.exists():
        return set()
    if (sysdir / "partition").exists():
        return {sysdir.resolve().parent.name}
    slaves = list((sysdir / "slaves").glob("*")) if (sysdir / "slaves").exists() else []
    if slaves:
        disks = set()
        for s in slaves:
            disks |= base_disks(s.name)
        return disks
    return {devname}


def own_disks():
    """The disk(s) the stick itself runs from: everything behind /, /boot and /boot/efi.
    Checks skip these, so the stick never reports on (or touches) itself."""
    disks = set()
    for mnt in ("/", "/boot", "/boot/efi"):
        rc, out, _ = sh(["findmnt", "-no", "SOURCE", "--nofsroot", mnt])
        dev = out.strip()
        if rc == 0 and dev.startswith("/dev/"):
            disks |= base_disks(Path(os.path.realpath(dev)).name)
    return disks


def desktop_user():
    """The person at the keyboard (chiron re-runs itself as root via sudo)."""
    import pwd
    name = os.environ.get("SUDO_USER")
    if not name and os.environ.get("PKEXEC_UID"):
        name = pwd.getpwuid(int(os.environ["PKEXEC_UID"])).pw_name
    if not name:
        name = pwd.getpwuid(os.getuid()).pw_name
    return pwd.getpwnam(name)


def as_desktop_user(cmd):
    """Command list that runs `cmd` as the desktop user inside their graphical session."""
    u = desktop_user()
    env = ["env", f"DISPLAY={os.environ.get('DISPLAY') or ':0'}",
           f"XAUTHORITY={os.environ.get('XAUTHORITY') or os.path.join(u.pw_dir, '.Xauthority')}",
           f"DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{u.pw_uid}/bus", f"XDG_RUNTIME_DIR=/run/user/{u.pw_uid}"]
    if os.geteuid() == 0 and u.pw_uid != 0:
        return ["runuser", "-u", u.pw_name, "--", *env, *cmd]
    return [*env, *cmd]


def human_bytes(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1000 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1000
    return f"{n:.1f} TB"
