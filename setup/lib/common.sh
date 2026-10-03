# Shared helpers for Chiron Stick setup scripts. Source it; don't run it.

DRY_RUN=0
ARGS=()

# parse_args "$@": handles --dry-run, collects the rest into ARGS
parse_args() {
  for a in "$@"; do
    case "$a" in
      --dry-run) DRY_RUN=1 ;;
      *) ARGS+=("$a") ;;
    esac
  done
}

# run <command...>: runs it, or only prints it with --dry-run
run() {
  if [ "$DRY_RUN" = 1 ]; then printf '[dry-run] %s\n' "$*"; else "$@"; fi
}

die() { echo "ERROR: $*" >&2; exit 1; }

# confirm_yes <message>: the user must type exactly "yes" (CLAUDE.md safety rule 3)
confirm_yes() {
  printf '%s\nType yes to continue: ' "$1"
  read -r answer
  [ "$answer" = yes ] || die "not confirmed, nothing changed"
}

# check_target <by-id path> <drive serial>: CLAUDE.md safety rule 2.
# Stops unless the path is a USB by-id path, the drive serial matches, the size is in the
# expected range (default 100-130 GB, override with TARGET_MIN_GB/TARGET_MAX_GB) and nothing is mounted.
check_target() {
  local dev=$1 serial=$2 real tran ser size
  case "$dev" in /dev/disk/by-id/usb-*) ;; *) die "use the /dev/disk/by-id/usb-... path, not $dev" ;; esac
  real=$(readlink -f "$dev")
  [ -b "$real" ] || die "no such block device: $dev"
  lsblk -o NAME,SIZE,MODEL,SERIAL,TRAN,MOUNTPOINTS "$dev"
  echo "$dev -> $real"
  tran=$(lsblk -dno TRAN "$dev")
  [ "$tran" = usb ] || die "not a USB disk (TRAN=$tran)"
  ser=$(lsblk -dno SERIAL "$dev")
  [ "$ser" = "$serial" ] || die "drive serial is '$ser', expected '$serial'"
  size=$(lsblk -bdno SIZE "$dev")
  [ "$size" -ge $(( ${TARGET_MIN_GB:-100} * 1000000000 )) ] && [ "$size" -le $(( ${TARGET_MAX_GB:-130} * 1000000000 )) ] ||
    die "unexpected size: $size bytes"
  if lsblk -no MOUNTPOINTS "$dev" | grep -q .; then die "a partition of the target is mounted"; fi
  echo "target checks passed: USB, serial $ser, $size bytes, nothing mounted"
}
