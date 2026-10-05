"""Disk scan (Tete picked the disk deep-dive, 2026-10-05): read samples spread across the whole drive
and measure each one. A healthy drive reads at an even speed from start to end (hard disks slow down
gently towards the end); a failing one has areas that read slowly or not at all. Read-only: the
drive is only ever opened with O_RDONLY, and O_DIRECT keeps the page cache from flattering it."""
import mmap
import os
import statistics
import time

SAMPLES = 200
CHUNK = 32 * 1024 * 1024   # bytes per sample: big enough to measure speed, not seek time
ALIGN = 4096


def scan(dev, size, samples=SAMPLES, chunk=CHUNK, emit=None, name=None):
    """Read `samples` chunks evenly spaced over the device. emit(kind, **data) gets each sample as a
    "scan" event for the doctor's live graph. Returns {"samples": [...], "errors", "median_mbps", …}."""
    emit = emit or (lambda *a, **k: None)
    chunk = min(chunk, max(ALIGN, (size // samples) // ALIGN * ALIGN))
    try:
        fd = os.open(dev, os.O_RDONLY | os.O_DIRECT)
    except OSError:
        fd = os.open(dev, os.O_RDONLY)  # files and filesystems without O_DIRECT (tests)
    buf = mmap.mmap(-1, chunk)  # page-aligned, as O_DIRECT needs
    out, started = [], time.monotonic()
    try:
        span = max(0, size - chunk)
        for i in range(samples):
            off = int(span * i / max(1, samples - 1)) // ALIGN * ALIGN
            t0 = time.perf_counter()
            try:
                n = os.preadv(fd, [buf], off)
                dt = time.perf_counter() - t0
                mbps = round(n / dt / 1e6, 1) if dt > 0 and n else None
                err = n == 0
            except OSError:
                mbps, err = None, True
            out.append({"offset": off, "mbps": mbps, "error": err})
            emit("scan", id="disk_scan", disk=name or os.path.basename(dev), i=i, n=samples, mbps=mbps, error=err,
                 pos=round(off / size, 4) if size else 0)
    finally:
        os.close(fd)
        buf.close()
    speeds = [s["mbps"] for s in out if s["mbps"]]
    return {"samples": out, "errors": sum(1 for s in out if s["error"]), "chunk": chunk,
            "median_mbps": round(statistics.median(speeds), 1) if speeds else None,
            "min_mbps": min(speeds) if speeds else None, "max_mbps": max(speeds) if speeds else None,
            "seconds": round(time.monotonic() - started, 1)}


def grade(res):
    """(status, summary): red if any area can't be read; amber if more than 3% of the samples read
    at under 30% of the drive's median speed (slow areas: worn or failing); green otherwise."""
    samples, med = res["samples"], res.get("median_mbps")
    n = len(samples) or 1
    if res["errors"]:
        return "red", f"{res['errors']} of {n} areas couldn't be read: the drive is failing"
    if not med:
        return "n/a", "no speed measured"
    slow = [s for s in samples if s["mbps"] is not None and s["mbps"] < 0.3 * med]
    speeds = [s["mbps"] for s in samples if s["mbps"] is not None]
    lo, hi = res.get("min_mbps") or min(speeds), res.get("max_mbps") or max(speeds)
    if len(slow) > 0.03 * n:
        return "yellow", f"{len(slow)} of {n} areas read slowly (under 30% of the usual {med:.0f} MB/s)"
    return "green", f"every area readable, {lo:.0f}–{hi:.0f} MB/s (median {med:.0f})"


def run(ctx, emit=None):
    """Scan every drive except the stick's own: one Result each."""
    import csv
    import io
    from chiron.checks.storage import list_disks
    from chiron.model import Result, Status
    from chiron.util import human_bytes
    results = []
    for d in list_disks(ctx.own):
        dev, size = f"/dev/{d['name']}", int(d["size"])
        label = f"{(d.get('model') or 'Disk').strip()} ({human_bytes(size)})"
        try:
            res = scan(dev, size, emit=emit, name=d["name"])
        except OSError as err:
            results.append(Result("disk_scan", f"Disk scan: {label}", Status.NA, f"couldn't open the drive: {err}"))
            continue
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=["offset", "mbps", "error"])
        w.writeheader()
        w.writerows(res["samples"])
        ctx.save_raw(f"disk-scan-{d['name']}.csv", buf.getvalue())
        status, summary = grade(res)
        cls = "nvme" if d["name"].startswith("nvme") else ("hdd" if d.get("rota") in (True, "1", 1) else "ssd")
        ev = {"device": dev, "model": (d.get("model") or "").strip(), "size_bytes": size, "class": cls,
              "transport": d.get("tran"), "median_mbps": res["median_mbps"], "min_mbps": res["min_mbps"],
              "max_mbps": res["max_mbps"], "unreadable_areas": res["errors"], "samples": len(res["samples"]),
              "seconds": res["seconds"], "curve": [s["mbps"] for s in res["samples"]]}
        results.append(Result("disk_scan", f"Disk scan: {label}", Status(status), summary, ev))
    if not results:
        results.append(Result("disk_scan", "Disk scan", Status.NA, "No disks found (other than this stick)."))
    return results
