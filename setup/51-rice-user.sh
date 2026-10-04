#!/bin/sh
# Phase 4R, user part: set up the "Clinic Night" desktop for the person running it: panels, keys,
# fonts, autostart, wallpaper rotation, first theme. Run it as the desktop user, inside the graphical
# session, after setup/50-rice.sh. Then `chiron walls update` downloads the wallpaper collection.
set -eu
[ "$(id -u)" != 0 ] || { echo "run this as the desktop user, not root" >&2; exit 1; }
[ -x /opt/chiron/rice/chiron-rice ] || { echo "run setup/50-rice.sh (as root) first" >&2; exit 1; }
exec /opt/chiron/rice/chiron-rice install-user
