"""The `chiron` command. Every user-facing Chiron Stick command is a subcommand (CLAUDE.md decision 11)."""
import argparse
import datetime
import getpass
import json
import os
import re
import shutil
import sys
from pathlib import Path

from chiron import __version__, history, mount, rice
from chiron.checks import TITLES, run_all
from chiron.events import Events
from chiron.checks.system import identity
from chiron.model import Context
from chiron.report import write_all
from chiron.util import desktop_user, is_root, own_disks

HELP = """Chiron Stick: a portable PC doctor.

  chiron doctor                       the doctor launcher: run every check from one window
  chiron report [--quick]             read-only health check (about 3 minutes; --quick skips the disk speed test)
  chiron stress [--minutes 10]        load tests with live safety limits (--no-gpu, --no-ram)
  chiron full [--minutes 10]          report + stress + one combined verdict
  chiron compare [machine]            what changed since this machine's previous check
  chiron mount-ro <device>            mount a partition read-only (BitLocker: the owner types the recovery key)
  chiron umount <mountpoint|all>      undo mount-ro
  chiron forget <machine>             delete every report and the history of one machine
  chiron rice <apply|pick|random|mode|pause|resume> …   desktop theme
  chiron walls update                 download or update the wallpaper collections
  chiron walls review                 see every wallpaper and keep it or remove it
  chiron walls status                 what's downloaded, kept and removed
  chiron help                         this list

Reports go to ~/reports/<date>_<maker>-<model>/ (report.md/.html/.json, owner-summary.html, raw/)."""

COLOR = {"green": "\033[32m", "yellow": "\033[33m", "red": "\033[31m", "n/a": "\033[90m", "info": "\033[36m"}
RESET = "\033[0m"


def ensure_root(argv):
    """Re-run this command as root through sudo (the password is asked once)."""
    if is_root():
        return
    pkg_parent = str(Path(__file__).resolve().parent.parent)
    os.execvp("sudo", ["sudo", "--preserve-env=DISPLAY,XAUTHORITY,WAYLAND_DISPLAY", "env",
                       f"PYTHONPATH={pkg_parent}", sys.executable, "-m", "chiron", *argv])


def reports_root():
    return Path(desktop_user().pw_dir) / "reports"


def _slug(text):
    return re.sub(r"[^A-Za-z0-9]+", "-", text or "").strip("-")[:40] or "unknown"


def _chown(path):
    """Reports belong to the person, not root."""
    if not is_root():
        return
    u = desktop_user()
    for p in [path, *path.rglob("*")]:
        try:
            os.chown(p, u.pw_uid, u.pw_gid)
        except OSError:
            pass


def print_summary(report, folder):
    tty = sys.stdout.isatty()
    width = shutil.get_terminal_size((100, 20)).columns
    print()
    for r in report["results"]:
        st = r["status"]
        label = f"{COLOR[st]}{st:>6}{RESET}" if tty else f"{st:>6}"
        line = f"{label}  {r['title']}: {r['summary']}"
        print(line if len(line) < width + 10 else line[:width + 8] + "…")
    o = report["overall"]
    print(f"\nOverall: {COLOR[o] if tty else ''}{o}{RESET if tty else ''}")
    if report.get("compare"):
        print(f"\nChanges since {report['compare_with']}:")
        for c in report["compare"]:
            print(f"  {c['name']}: {c['before']} -> {c['after']}")
    print(f"\nReport: {folder}/report.html\nOwner summary (Thai + English, printable): {folder}/owner-summary.html")


def unique_folder(folder):
    """folder, or folder-2, -3, …: two checks in the same minute keep both reports."""
    n, out = 1, folder
    while out.exists():
        n += 1
        out = folder.with_name(f"{folder.name}-{n}")
    return out


def collect(with_report=True, with_stress=False, quick=False, minutes=10, gpu=True, ram=True, ev=None):
    """ev: an Events stream (chiron --events, for the doctor launcher) instead of text."""
    from chiron import checks
    from chiron.stress import STEPS, stress
    from chiron.stress import steps as stress_steps
    ev = ev or Events()
    root = reports_root()
    ident = identity()
    now = datetime.datetime.now().astimezone()
    folder = unique_folder(root / f"{now:%Y-%m-%d_%H%M}_{_slug(ident.get('sys_vendor'))}-{_slug(ident.get('product_name'))}")
    ctx = Context(raw_dir=folder / "raw", quick=quick, own=own_disks())
    modules = checks.MODULES if with_report else ["system"]
    planned = [{"id": m, "title": TITLES[m]} for m in modules]
    if with_stress:
        planned += [{"id": k, "title": STEPS[k]} for k in stress_steps(gpu=gpu, ram=ram)]
    ev.emit("start", mode="full" if with_report and with_stress else "stress" if with_stress else "report",
            machine={k: ident.get(k) for k in ("sys_vendor", "product_name")}, steps=planned,
            minutes=minutes if with_stress else None, quick=quick)
    ev.say(f"Chiron {__version__}: checking {ident.get('sys_vendor') or ''} {ident.get('product_name') or ''}".rstrip())
    from chiron import specs
    try:
        sheet = specs.collect(ctx)
    except Exception as err:  # noqa: BLE001 - a spec sheet that fails must not stop the check
        sheet = {"error": str(err)}
    ev.emit("specs", lines=specs.lines(sheet))
    results = run_all(ctx, only=set(modules), progress=ev.say, on_check=lambda m: ev.emit("check", id=m),
                      on_result=lambda m, r: ev.emit("result", id=m, result=r.to_dict()))
    if with_stress:
        ev.say("Stress tests:")
        results += stress(ctx, minutes=minutes, gpu=gpu, ram=ram, progress=ev.say, emit=ev.emit)
    dicts = [r.to_dict() for r in results]
    fp = history.fingerprint(ident)
    report = {"chiron": __version__, "created": now.isoformat(timespec="seconds"), "fingerprint": fp,
              "machine": {k: v for k, v in ident.items() if v and k not in ("board_serial", "product_uuid")},
              "results": dicts, "specs": sheet}
    prev = history.previous(root, fp)
    if prev:
        report["compare"] = history.compare(prev["metrics"], history.metrics(dicts))
        report["compare_with"] = prev["created"][:16].replace("T", " ")
    write_all(report, folder)
    history.record(root, fp, report["created"], folder.name, dicts)
    _chown(root)
    if ev.enabled:
        ev.emit("done", overall=report["overall"], folder=str(folder), compare=report.get("compare"),
                compare_with=report.get("compare_with"))
    else:
        print_summary(report, folder)
    return 1 if report["overall"] == "red" else 0


def cmd_compare(args):
    root = reports_root()
    fp = args.machine or history.fingerprint(identity())
    hist_dir = root / "history"
    matches = [d for d in hist_dir.glob("*") if d.name.startswith(fp)] if hist_dir.exists() else []
    if not matches:
        print("No history for this machine yet: run `chiron report` first.")
        return 1
    runs = json.loads((matches[0] / "runs.json").read_text())
    if len(runs) < 2:
        print(f"Only one check so far ({runs[0]['created'][:16]}): nothing to compare yet.")
        return 0
    rows = history.compare(runs[-2]["metrics"], runs[-1]["metrics"])
    print(f"Changes from {runs[-2]['created'][:16]} to {runs[-1]['created'][:16]}:")
    for c in rows or [{"name": "nothing changed", "before": "", "after": ""}]:
        print(f"  {c['name']}: {c['before']} -> {c['after']}")
    return 0


def cmd_mount_ro(args):
    dev = args.device
    key = None
    if mount.fstype(dev) == "BitLocker":
        print("This partition is encrypted with BitLocker. The owner types the recovery key (it isn't stored).")
        key = getpass.getpass("BitLocker recovery key: ").strip()
    try:
        mp = mount.mount_ro(dev, key)
    except mount.MountError as e:
        print(f"chiron mount-ro: {e}", file=sys.stderr)
        return 1
    print(f"{dev} is mounted read-only at {mp}\nWhen you're done: chiron umount {mp}")
    return 0


def cmd_umount(args):
    if args.target == "all":
        mount.umount_all()
        print("All read-only mounts removed.")
        return 0
    try:
        mount.umount(args.target)
    except mount.MountError as e:
        print(f"chiron umount: {e}", file=sys.stderr)
        return 1
    print(f"Unmounted {args.target}.")
    return 0


def cmd_forget(args):
    res = history.forget(reports_root(), args.machine)
    if not res:
        print(f"No machine matches '{args.machine}' (use a report folder name or the fingerprint from report.json).")
        return 1
    fp, deleted = res
    print(f"Forgot machine {fp}: deleted {len(deleted)} report(s) and its history.")
    return 0


def cmd_rice(args):
    rc, out = rice.call(*args.args)
    print(out)
    return 0 if rc == 0 else 1


def cmd_walls(args):
    return rice.run("walls", args.action)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    p = argparse.ArgumentParser(prog="chiron", add_help=False)
    p.add_argument("--version", action="version", version=f"chiron {__version__}")
    p.add_argument("--events", action="store_true", help=argparse.SUPPRESS)  # JSON lines for `chiron doctor`
    sub = p.add_subparsers(dest="cmd")
    d = sub.add_parser("doctor"); d.add_argument("--demo", action="store_true")
    r = sub.add_parser("report"); r.add_argument("--quick", action="store_true")
    for name in ("stress", "full"):
        s = sub.add_parser(name)
        s.add_argument("--minutes", type=float, default=10)
        s.add_argument("--no-gpu", action="store_true")
        s.add_argument("--no-ram", action="store_true")
        s.add_argument("--quick", action="store_true")
    c = sub.add_parser("compare"); c.add_argument("machine", nargs="?")
    m = sub.add_parser("mount-ro"); m.add_argument("device")
    u = sub.add_parser("umount"); u.add_argument("target")
    f = sub.add_parser("forget"); f.add_argument("machine")
    ri = sub.add_parser("rice"); ri.add_argument("args", nargs=argparse.REMAINDER)
    w = sub.add_parser("walls"); w.add_argument("action", choices=["update", "review", "status"])
    sub.add_parser("help")
    args = p.parse_args(argv)

    if args.cmd in (None, "help"):
        print(HELP)
        return 0
    if args.cmd == "doctor":
        from chiron import doctor  # GTK: only imported for the window, never for the checks
        return doctor.main(demo=args.demo)
    if args.cmd in ("report", "stress", "full", "compare", "mount-ro", "umount"):
        ensure_root(argv)
    ev = None
    if args.events and args.cmd in ("report", "stress", "full"):
        from chiron import events
        ev = events.start()
    try:
        if args.cmd == "report":
            return collect(quick=args.quick, ev=ev)
        if args.cmd in ("stress", "full"):
            return collect(with_report=args.cmd == "full", with_stress=True, quick=args.quick,
                           minutes=args.minutes, gpu=not args.no_gpu, ram=not args.no_ram, ev=ev)
        return {"compare": cmd_compare, "mount-ro": cmd_mount_ro, "umount": cmd_umount, "forget": cmd_forget,
                "rice": cmd_rice, "walls": cmd_walls}[args.cmd](args)
    except KeyboardInterrupt:
        if ev:
            ev.emit("stopped")
        print("\nStopped.")
        return 130
