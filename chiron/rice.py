"""Hooks into the desktop theme ("rice", Phase 4R). Tests pause wallpaper rotation and the
compositor so they run clean, and restore them afterwards (CLAUDE.md decision 10). Until the rice
is installed these are no-ops, and `chiron rice …` says so."""
from pathlib import Path

from chiron.util import as_desktop_user, sh

RICE = Path("/opt/chiron/rice")


def available():
    return (RICE / "chiron-rice").exists()


def call(*args, timeout=60):
    """Run the rice tool as the desktop user. Returns (rc, output)."""
    if not available():
        return 127, "The desktop theme (Phase 4R) isn't installed on this stick yet."
    rc, out, err = sh(as_desktop_user([str(RICE / "chiron-rice"), *args]), timeout=timeout)
    return rc, (out + err).strip()


def pause():
    if available():
        call("pause")


def resume():
    if available():
        call("resume")
