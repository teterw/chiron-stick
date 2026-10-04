"""chiron doctor: the doctor launcher, "Star chart" (Tete's pick, 2026-10-04).

Every check is a star; the stars sit in a ring on the night sky made from the person's own wallpaper,
joined like a constellation. A check lights its star green, amber or red as its findings come in;
the centre shows the progress, live CPU readings during the stress test, then the verdict.

Runs as the desktop user. The checks run as root through pkexec (`chiron --events …`, see
chiron/events.py), so the password goes to the system's own dialog, never through this window.
Drawn with cairo on the CPU (works without a GPU driver), and it redraws only a few times a second
while a stress test runs, so it doesn't take CPU time from the test. Verdict colours are fixed
(CLAUDE.md decision 10): only the lines, the ring and the buttons take the theme's accent."""
import datetime
import os
import pwd
import sys
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path

from chiron import doctor_model as dm
from chiron.checks import MODULES, TITLES

HERE = Path(__file__).resolve().parent
RICE = HERE.parent / "rice"  # /opt/chiron/rice on the stick
CHIRON = "/usr/local/bin/chiron"
REPORTS = Path.home() / "reports"
LOG = Path.home() / ".cache" / "chiron" / "doctor.log"

FONT, MONO = "Noto Sans", "JetBrainsMono Nerd Font"
FG, MUTED, WAIT = (0.93, 0.92, 0.96), (0.58, 0.55, 0.68), (0.30, 0.28, 0.40)
INFO, NA = (0.86, 0.84, 0.95), (0.48, 0.46, 0.58)
VIOLET = (0.545, 0.361, 0.965)
VERDICT = {"green": (0.13, 0.77, 0.37), "yellow": (0.96, 0.62, 0.04), "red": (0.94, 0.27, 0.27)}  # fixed
WORDS = {"green": "All good", "yellow": "Worth a look", "red": "Problem found"}
ACTIONS = [("Health check", "about 3 min · reads only", ["report"]),
           ("Quick check", "1 min · no disk speed test", ["report", "--quick"]),
           ("Stress test", "10 min under full load", ["stress"]),
           ("Check + stress", "everything · about 13 min", ["full"])]


def colour(status, accent):
    return VERDICT.get(status) or {"run": accent, "info": INFO, "na": NA}.get(status, WAIT)


def load_module(name, path):
    loader = SourceFileLoader(name, str(path))
    mod = module_from_spec(spec_from_loader(name, loader))
    loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- the person and the machine

def greeting(now=None):
    h = (now or datetime.datetime.now()).hour
    part = "night" if h < 5 else "morning" if h < 12 else "afternoon" if h < 18 else "evening"
    return f"Good {part}, {pwd.getpwuid(os.getuid()).pw_name}"


def this_machine():
    """({sys_vendor, product_name}, "CPU · RAM"): what a normal user can read."""
    def rd(p):
        try:
            return Path(p).read_text().strip()
        except OSError:
            return ""
    m = {"sys_vendor": rd("/sys/class/dmi/id/sys_vendor"), "product_name": rd("/sys/class/dmi/id/product_name")}
    cpu = next((l.split(":", 1)[1].strip() for l in rd("/proc/cpuinfo").splitlines() if l.startswith("model name")), "")
    for junk in ("(R)", "(TM)", "CPU", "Processor", "13th Gen ", "12th Gen ", "11th Gen "):
        cpu = cpu.replace(junk, "")
    cpu = " ".join(cpu.split("@")[0].split())
    kb = next((int(l.split()[1]) for l in rd("/proc/meminfo").splitlines() if l.startswith("MemTotal")), 0)
    return m, " · ".join(x for x in (cpu, f"{round(kb / 1048576)} GB" if kb else "") if x)


def personal():
    """(wallpaper, accent): the desktop's current wallpaper and its theme accent (chiron-rice)."""
    try:
        rice = load_module("chiron_rice", RICE / "chiron-rice")
        wall = rice.load_state().get("wallpaper")
        if wall and Path(wall).is_file():
            return Path(wall), tuple(rice.derive(rice.run_wallust(wall))["accent"])
    except (Exception, SystemExit):  # noqa: BLE001 - no theme: the stick's own violet sky
        pass
    return None, VIOLET


def main(demo=False):
    try:
        import cairo  # noqa: F401
        import gi
        gi.require_version("Gtk", "3.0")
        gi.require_version("Gdk", "3.0")
        gi.require_version("PangoCairo", "1.0")
        from gi.repository import Gtk  # noqa: F401
        from PIL import Image  # noqa: F401
    except (ImportError, ValueError) as err:
        print(f"chiron doctor: can't open the window ({err}). The checks still work in a terminal: chiron help",
              file=sys.stderr)
        return 3
    from chiron import doctor_window
    return doctor_window.run(demo)
