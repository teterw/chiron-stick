"""chiron doctor: the doctor launcher. A star chart of every check in a terminal / HUD style
(doctor_scene.py), played back at a watchable pace (doctor_model.Pacer).

Runs as the desktop user. The checks run as root through pkexec (`chiron --events …`, see
chiron/events.py), so the password goes to the system's own dialog, never through this window.
Drawn with cairo on the CPU (works without a GPU driver), and it redraws only 8 times a second
while a stress test runs, so it doesn't take CPU time from the test."""
import os
import sys
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path


HERE = Path(__file__).resolve().parent
RICE = HERE.parent / "rice"  # /opt/chiron/rice on the stick
CHIRON = "/usr/local/bin/chiron"
REPORTS = Path.home() / "reports"
LOG = Path.home() / ".cache" / "chiron" / "doctor.log"

VIOLET = (0.545, 0.361, 0.965)  # Chiron violet: the accent when there is no desktop theme


def load_module(name, path):
    loader = SourceFileLoader(name, str(path))
    mod = module_from_spec(spec_from_loader(name, loader))
    loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- the person and the machine

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
