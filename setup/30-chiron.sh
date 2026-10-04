#!/bin/bash
# Phase 5: install the chiron tool on the stick: the package in /opt/chiron/chiron and the
# `chiron` command in /usr/local/bin. Run it ON the stick, as root, from a copy of this repo.
# Usage: sudo setup/30-chiron.sh [--dry-run]
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/.." && pwd)
. "$HERE/lib/common.sh"
parse_args "$@"
[ "$(id -u)" = 0 ] || [ "$DRY_RUN" = 1 ] || die "run as root on the stick"
command -v python3 >/dev/null || die "python3 is missing"

echo "===== 1. Unit tests (grading logic)"
(cd "$REPO" && python3 -m unittest discover -s tests) || die "unit tests failed: not installing"

echo "===== 2. Package -> /opt/chiron/chiron"
run install -d -m 0755 /opt/chiron
run rm -rf /opt/chiron/chiron.new
run cp -r "$REPO/chiron" /opt/chiron/chiron.new
run find /opt/chiron/chiron.new -name __pycache__ -prune -exec rm -rf {} +
run rm -rf /opt/chiron/chiron
run mv /opt/chiron/chiron.new /opt/chiron/chiron

echo "===== 3. The chiron command"
WRAPPER='#!/bin/sh
# Chiron Stick: see `chiron help`
PYTHONPATH=/opt/chiron exec python3 -m chiron "$@"'
if [ "$DRY_RUN" = 1 ]; then
  echo "[dry-run] write /usr/local/bin/chiron"
else
  printf '%s\n' "$WRAPPER" > /usr/local/bin/chiron
  chmod 0755 /usr/local/bin/chiron
  /usr/local/bin/chiron --version
fi
echo "===== 4. The doctor launcher: password rule and menu entry"
# pkexec asks once and remembers it for a few minutes (auth_admin_keep), only for /usr/local/bin/chiron
run install -m 0644 "$REPO/stick/usr/share/polkit-1/actions/org.chironstick.chiron.policy" /usr/share/polkit-1/actions/
run install -m 0644 "$REPO/stick/usr/share/applications/chiron-doctor.desktop" /usr/share/applications/
echo "Installed. Try: chiron help, or Chiron Doctor in the menu"
