#!/usr/bin/env python3
"""Render Chiron Doctor's demo run to pictures, without a display or root: for checking the look and
the pacing on any machine, and for README screenshots.

  tools/doctor-frames.py OUT_DIR [--wall IMAGE] [--accent '#8b5cf6'] [--size 1280x800]
                         [--fps 30] [--at 1.5,7,20] [--video]

--at renders single frames at those seconds; otherwise every frame of the whole run (until the
verdict has settled). --video joins them into OUT_DIR/doctor.mp4 with ffmpeg."""
import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cairo  # noqa: E402

from chiron import doctor_model as dm  # noqa: E402
from chiron.doctor_scene import Scene  # noqa: E402


def hex2rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--wall")
    ap.add_argument("--accent", default="#8b5cf6")
    ap.add_argument("--size", default="1280x800")
    ap.add_argument("--fps", type=float, default=30)
    ap.add_argument("--at")
    ap.add_argument("--video", action="store_true")
    ap.add_argument("--detail", help="open this node's findings (e.g. storage)")
    a = ap.parse_args()
    W, H = (int(v) for v in a.size.split("x"))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    machine = {"sys_vendor": "Acer", "product_name": "Aspire A515-58M"}
    scene = Scene("teterw", machine, "Intel Core i5-13420H · 16 GB", hex2rgb(a.accent), a.wall,
                  {"created": "2026-09-12T10:05:00+07:00", "overall": "yellow", "folder": Path("/nonexistent")})
    # the demo's events with the times they'd arrive from chiron, starting when "Enter" is pressed at 1.5 s
    arrivals, t = [], 1.5
    for delay, e in dm.demo_events():
        t += delay
        arrivals.append((t, e))
    pacer = dm.Pacer()
    times = [float(x) for x in a.at.split(",")] if a.at else None
    frame, now, end = 0, 0.0, None
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    while True:
        while arrivals and arrivals[0][0] <= now:
            pacer.push(arrivals.pop(0)[1])
        pacer.update(now)
        run = pacer.run
        if run.phase == "done" and end is None:
            end = now + 4.0  # let the verdict type in and settle
        want = times is None or any(abs(now - x) < 0.5 / a.fps for x in times)
        if want:
            cr = cairo.Context(surf)
            scene.detail = a.detail if a.detail and pacer.run.star(a.detail) else None
            scene.render(cr, W, H, now, run)
            name = f"t{now:06.2f}.png" if times else f"f{frame:05d}.png"
            surf.write_to_png(str(out / name))
            frame += 1
        now += 1 / a.fps
        if (end is not None and now > end) or (times and now > max(times) + 0.1) or now > 600:
            break
    print(f"{frame} frames in {out}; the run reached the screen in {now:.1f} s")
    if a.video and not times:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(a.fps), "-i", str(out / "f%05d.png"),
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "22", str(out / "doctor.mp4")], check=True)
        print(f"video: {out / 'doctor.mp4'}")


if __name__ == "__main__":
    main()
