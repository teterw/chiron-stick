"""Hooks into the desktop theme ("rice", Phase 4R). Tests pause wallpaper rotation and the
compositor so they run clean, and restore them afterwards (CLAUDE.md decision 10). Until the rice
is installed these are no-ops, and `chiron rice …` says so."""
import json
import subprocess
from pathlib import Path

from chiron.util import as_desktop_user, sh

RICE = Path("/opt/chiron/rice")
MISSING = "The desktop theme (Phase 4R) isn't installed on this stick yet."


def available():
    return (RICE / "chiron-rice").exists()


def call(*args, timeout=60):
    """Run the rice tool as the desktop user. Returns (rc, output)."""
    if not available():
        return 127, MISSING
    rc, out, err = sh(as_desktop_user([str(RICE / "chiron-rice"), *args]), timeout=timeout)
    return rc, (out + err).strip()


def run(*args):
    """Like call(), for long or interactive jobs: the output goes straight to the terminal."""
    if not available():
        print(MISSING)
        return 127
    return subprocess.call(as_desktop_user([str(RICE / "chiron-rice"), *args]))


def pause():
    """Pause for a test. Returns True only if this call paused it, so a pause the person set
    themselves is still there after the test."""
    if not available():
        return False
    rc, out = call("status")
    try:
        if rc == 0 and json.loads(out).get("paused"):
            return False
    except ValueError:
        pass
    return call("pause")[0] == 0


def resume():
    if available():
        call("resume")
