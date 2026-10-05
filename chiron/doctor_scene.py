"""Chiron Doctor's picture: the star chart, styled like professional instrument software (Tete,
2026-10-05: the star chart in a terminal / techy style, with smooth, unhurried animation, and then
"too cartoonish, I want it to look professional").

Restraint is the style: a calm near-black surface tinted by the person's wallpaper, hairline links,
small flat nodes, a sans for words and a monospace for data, uppercase captions, status chips
(OK / WARN / FAIL) instead of glows, and motion that eases and fades instead of flashing. Every
check is a node on a wide ellipse; a light travels along the link to the next node, a thin arc spins
while it is checked, then the node takes its status colour and its finding fades in. A command
palette starts a run; a segmented ring shows progress and then the diagnosis; an activity log
records every event.

Only cairo and Pango: the window (doctor_window.py) and tools/doctor-frames.py both draw through
Scene.render(). Verdict colours are fixed (CLAUDE.md decision 10)."""
import colorsys
import datetime
import math
import time

import cairo
import gi

gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Pango, PangoCairo  # noqa: E402
from PIL import Image, ImageFilter, ImageOps  # noqa: E402

from chiron import doctor_model as dm  # noqa: E402
from chiron.checks import MODULES, TITLES  # noqa: E402

SANS = "Noto Sans, Inter, Cantarell, sans-serif"
MONO = "JetBrainsMono Nerd Font, JetBrains Mono, DejaVu Sans Mono, monospace"
BG = (0.043, 0.047, 0.059)
PANEL = (0.066, 0.071, 0.086)
FG = (0.90, 0.91, 0.93)
SUB = (0.60, 0.62, 0.67)
FAINT = (0.34, 0.36, 0.41)
HAIR = (1.0, 1.0, 1.0)  # hairlines: white at low alpha
VERDICT = {"green": (0.25, 0.79, 0.48), "yellow": (0.95, 0.69, 0.22), "red": (0.93, 0.36, 0.36)}  # fixed
INFO = (0.62, 0.66, 0.75)
CHIP = {"green": "OK", "yellow": "WARN", "red": "FAIL", "info": "INFO", "na": "N/A", "run": "RUN"}
WORDS = {"green": "All good", "yellow": "Worth a look", "red": "Problem found"}
MENU = [("Health check", "~3 min", ["report"], "Every check, read-only"),
        ("Quick check", "~1 min", ["report", "--quick"], "Skips the disk speed test"),
        ("Stress test", "10 min", ["stress"], "CPU, RAM and graphics under full load"),
        ("Check + stress", "~13 min", ["full"], "Everything, one combined verdict")]
SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
TAU = 2 * math.pi
SCAN_CYAN = (0.38, 0.78, 0.95)


def clamp(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, v))


def ease_out(t):
    return 1 - (1 - clamp(t)) ** 3


def ease_in_out(t):
    t = clamp(t)
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def scan_colour(accent):
    """The colour of whatever is being checked (the travelling light, the spinning arc, the running
    segment): the theme's accent, unless it could be mistaken for green, amber or red."""
    h, _l, sat = colorsys.rgb_to_hls(*accent)
    near = min(min(abs(h - v), 1 - abs(h - v)) for v in (0.0, 0.11, 0.39))  # red, amber, green hues
    return accent if near >= 0.1 and sat >= 0.2 else SCAN_CYAN


def status_of(st):
    """What a node shows: its final status, its verdict as soon as a finding is in, or run/wait."""
    if st.status not in ("wait", "run"):
        return st.status
    if st.revealed_at is not None:
        return st.verdict
    return st.status


def colour(status, scan):
    return VERDICT.get(status) or {"run": scan, "info": INFO, "na": FAINT}.get(status, FAINT)


def surface(im):
    im = im.convert("RGBA")
    w, h = im.size
    return cairo.ImageSurface.create_for_data(bytearray(im.tobytes("raw", "BGRa")), cairo.FORMAT_ARGB32, w, h, w * 4)


def backdrop(wall, w, h):
    """A calm near-black surface, faintly tinted by the person's wallpaper."""
    base = Image.new("RGB", (w, h), tuple(int(c * 255) for c in BG))
    if wall:
        try:
            with Image.open(wall) as src:
                src.draft("RGB", (w // 8, h // 8))
                im = ImageOps.fit(src.convert("RGB"), (max(32, w // 16), max(18, h // 16)), Image.BILINEAR)
            im = im.filter(ImageFilter.GaussianBlur(3)).resize((w, h), Image.BILINEAR)
            base = Image.blend(base, im, 0.07)
        except OSError:
            pass
    return surface(base)


class Scene:
    def __init__(self, user, machine, spec, accent, wall=None, last=None):
        self.user, self.machine, self.spec, self.accent, self.wall, self.last = user, machine, spec, accent, wall, last
        self.scan = scan_colour(accent)
        self.bg = self.bg_size = None
        self.hits = []            # (x, y, w, h, action) for the window's clicks
        self.menu_sel = 0
        self.hover = None
        self.detail = None        # node id whose findings are shown
        self.shown = 0.0          # progress, eased
        self.last_now = None
        self.last_seen = None

    # ------------------------------------------------ drawing helpers

    def layout(self, cr, s, size, font=SANS, weight="", spacing=0.0, width=None):
        layout = PangoCairo.create_layout(cr)
        layout.set_font_description(Pango.FontDescription(f"{font} {weight} {size:.1f}px"))
        if spacing:
            attrs = Pango.AttrList()
            attrs.insert(Pango.attr_letter_spacing_new(int(spacing * Pango.SCALE)))
            layout.set_attributes(attrs)
        layout.set_text(s, -1)
        if width:
            layout.set_width(int(max(1, width) * Pango.SCALE))
            layout.set_ellipsize(Pango.EllipsizeMode.END)
        return layout

    def text(self, cr, s, x, y, size, color, alpha=1.0, font=SANS, weight="", align="left", width=None, spacing=0.0):
        layout = self.layout(cr, s, size, font, weight, spacing, width)
        w, h = layout.get_pixel_size()
        if align == "center":
            x -= w / 2
        elif align == "right":
            x -= w
        cr.set_source_rgba(*color, alpha)
        cr.move_to(x, y)
        PangoCairo.show_layout(cr, layout)
        cr.new_path()
        return w, h

    def caption(self, cr, s, x, y, scale, color=SUB, alpha=1.0, align="left"):
        """Small uppercase label with tracking: section titles."""
        return self.text(cr, s.upper(), x, y, 10.5 * scale, color, alpha, weight="Semi-Bold", align=align, spacing=1.2 * scale)

    def hline(self, cr, x0, x1, y, a=0.08, width=1.0):
        cr.set_source_rgba(*HAIR, a)
        cr.set_line_width(width)
        cr.move_to(x0, round(y) + 0.5)
        cr.line_to(x1, round(y) + 0.5)
        cr.stroke()

    def box(self, cr, x, y, w, h, fill=PANEL, fill_a=0.92, line_a=0.08, r=6):
        r = min(r, w / 2, h / 2)
        cr.new_sub_path()
        cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
        cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
        cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
        cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
        cr.close_path()
        cr.set_source_rgba(*fill, fill_a)
        cr.fill_preserve()
        cr.set_source_rgba(*HAIR, line_a)
        cr.set_line_width(1)
        cr.stroke()

    def chip_width(self, cr, status, s):
        return 10 * s + self.layout(cr, CHIP.get(status, ""), 10.5 * s, MONO, "Bold").get_pixel_size()[0]

    def chip(self, cr, status, x, y, scale, align="left", alpha=1.0):
        """A coloured dot and a status word: ● OK / ● WARN / ● FAIL."""
        col = colour(status, self.scan)
        word = CHIP.get(status, "")
        total = self.chip_width(cr, status, scale)
        x0 = x - (total if align == "right" else total / 2 if align == "center" else 0)
        cr.set_source_rgba(*col, alpha)
        cr.new_path()
        cr.arc(x0 + 3.5 * scale, y + 7.5 * scale, 3 * scale, 0, TAU)
        cr.fill()
        self.text(cr, word, x0 + 10 * scale, y + 0.5 * scale, 10.5 * scale, col, alpha, font=MONO, weight="Bold")
        return total

    # ------------------------------------------------ main

    def render(self, cr, W, H, now, run, waiting=None, under_load=False):
        dt = 0.0 if self.last_now is None else clamp(now - self.last_now, 0, 0.2)
        self.last_now = now
        s = max(0.6, min(W / 1280, H / 800))
        if self.bg_size != (W, H):
            self.bg, self.bg_size = backdrop(self.wall, W, H), (W, H)
        cr.set_source_surface(self.bg, 0, 0)
        cr.paint()
        self.hits = []
        gap = 0.0 if self.last_seen is None else max(0.0, now - self.last_seen)  # any gap, also long ones
        self.last_seen = now
        self.shown += (run.progress() - self.shown) * clamp(gap * 3)
        pad = 28 * s
        head = 70 * s
        log_top = H - 172 * s
        self.header(cr, W, s, now, run, pad, head)
        top, bottom = head + 18 * s, log_top - 18 * s
        cx, cy = W / 2, (top + bottom) / 2
        ry = (bottom - top) / 2 - 44 * s
        rx = min(W * 0.33, ry * 2.0, W / 2 - pad - 250 * s)
        self.chart(cr, W, s, now, run, cx, cy, rx, ry)
        if run.phase == "idle":
            self.palette(cr, s, now, cx, cy, waiting)
        elif run.phase == "running":
            self.progress(cr, s, now, run, cx, cy)
        else:
            self.diagnosis(cr, s, now, run, cx, cy)
        self.activity(cr, W, H, s, now, run, pad, log_top, waiting)
        if self.detail:
            self.details(cr, W, H, s, run, cx, cy)

    # ------------------------------------------------ header

    def header(self, cr, W, s, now, run, pad, head):
        y = 20 * s
        w, _ = self.text(cr, "CHIRON", pad, y, 15 * s, FG, weight="Bold", spacing=2.2 * s)
        self.text(cr, "Diagnostics", pad + w + 12 * s, y + 0.5 * s, 15 * s, SUB)
        stamp = datetime.datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
        self.text(cr, f"{self.user}@chiron  ·  {stamp}", pad, y + 24 * s, 11.5 * s, FAINT, font=MONO)
        name = " ".join(v for v in (self.machine.get("sys_vendor"), self.machine.get("product_name")) if v) or "This computer"
        self.text(cr, name, W - pad, y, 14 * s, FG, weight="Medium", align="right", width=560 * s)
        self.text(cr, self.spec, W - pad, y + 23 * s, 11.5 * s, SUB, font=MONO, align="right")
        self.hline(cr, pad, W - pad, head)
        if run.phase == "running":
            el = int(now - (run.started_at or now))
            msg, col = f"Running  ·  {el // 60:d}:{el % 60:02d}", self.scan
        elif run.phase in ("done", "stopped", "failed") and run.started_at:
            el = int((run.ended_at or now) - run.started_at)
            msg, col = f"{'Complete' if run.phase == 'done' else run.phase.title()}  ·  {el // 60:d}:{el % 60:02d}", SUB
        else:
            msg, col = "Ready", SUB
        mw = self.layout(cr, msg.upper(), 10.5 * s, SANS, "Semi-Bold", 1.2 * s).get_pixel_size()[0]
        cr.set_source_rgba(*col, 1)
        cr.new_path()
        cr.arc(W / 2 - mw / 2 - 10 * s, y + 13.5 * s, 3 * s, 0, TAU)
        cr.fill()
        self.caption(cr, msg, W / 2, y + 6 * s, s, col, align="center")

    # ------------------------------------------------ the chart

    def stars(self, run):
        if run.stars:
            return run.stars
        return [dm.Star(m, TITLES[m]) for m in MODULES]

    def chart(self, cr, W, s, now, run, cx, cy, rx, ry):
        stars = self.stars(run)
        n = len(stars)
        pts = []
        for i in range(n):
            a = -math.pi / 2 + i * TAU / n
            k = 1.0 if i % 2 == 0 else 0.93
            pts.append((cx + rx * k * math.cos(a), cy + ry * k * math.sin(a), a))
        # hairline links; the path the light has travelled is a little brighter
        cr.set_line_width(1 * s)
        for i in range(n):
            j = (i + 1) % n
            (x1, y1, _), (x2, y2, _) = pts[i], pts[j]
            travelled = stars[i].status != "wait" and stars[j].status != "wait" and (j != 0 or run.phase == "done")
            if travelled and stars[j].status == "run" and stars[j].started_at is not None \
                    and now - stars[j].started_at < dm.Pacer.BEAM:
                travelled = False  # the light is still on its way: drawn below
            cr.set_source_rgba(*(self.scan if travelled else HAIR), 0.32 if travelled else 0.07)
            cr.move_to(x1, y1)
            cr.line_to(x2, y2)
            cr.stroke()
        cur = next((i for i, st in enumerate(stars) if st.status == "run"), None)
        if cur is not None and stars[cur].started_at is not None:
            p = ease_in_out((now - stars[cur].started_at) / dm.Pacer.BEAM)
            if p < 1.0:
                sx, sy = (pts[cur - 1][0], pts[cur - 1][1]) if cur > 0 else (cx, cy)
                tx, ty = pts[cur][0], pts[cur][1]
                hx, hy = sx + (tx - sx) * p, sy + (ty - sy) * p
                g = cairo.LinearGradient(sx, sy, hx, hy)
                g.add_color_stop_rgba(0, *self.scan, 0.0)
                g.add_color_stop_rgba(max(0.0, 1 - 60 * s / max(1.0, math.hypot(hx - sx, hy - sy))), *self.scan, 0.0)
                g.add_color_stop_rgba(1, *self.scan, 0.9)
                cr.set_source(g)
                cr.set_line_width(1.5 * s)
                cr.move_to(sx, sy)
                cr.line_to(hx, hy)
                cr.stroke()
                cr.set_source_rgba(*self.scan, 1)
                cr.new_path()
                cr.arc(hx, hy, 2.4 * s, 0, TAU)
                cr.fill()
        for i, (st, (x, y, ang)) in enumerate(zip(stars, pts)):
            self.node(cr, s, now, st, x, y)
            self.label(cr, W, s, now, st, i, x, y, ang, cx)
            if st.results:
                self.hits.append((x - 22 * s, y - 22 * s, 44 * s, 44 * s, f"node:{st.id}"))

    def node(self, cr, s, now, st, x, y):
        status = status_of(st)
        if st.status == "wait" or (st.status == "run" and st.started_at is not None
                                   and now - st.started_at < dm.Pacer.BEAM):
            cr.set_source_rgba(*HAIR, 0.22 if st.status == "wait" else 0.4)
            cr.set_line_width(1 * s)
            cr.new_path()
            cr.arc(x, y, 3.2 * s, 0, TAU)
            cr.stroke()
            return
        if st.status == "run" and st.revealed_at is None:
            # being checked: a thin arc turning around a small ring
            arrive = clamp((now - (st.started_at or now) - dm.Pacer.BEAM) / 0.3)
            cr.set_source_rgba(*self.scan, 0.25 * arrive)
            cr.set_line_width(1 * s)
            cr.new_path()
            cr.arc(x, y, 9 * s, 0, TAU)
            cr.stroke()
            a0 = now * 4.2
            cr.set_source_rgba(*self.scan, 0.95 * arrive)
            cr.set_line_width(1.6 * s)
            cr.new_path()
            cr.arc(x, y, 9 * s, a0, a0 + 1.6)
            cr.stroke()
            cr.set_source_rgba(*self.scan, 0.9)
            cr.new_path()
            cr.arc(x, y, 3 * s, 0, TAU)
            cr.fill()
            return
        # checked: the node takes its status colour; a faint ring settles around it
        col = colour(status, self.scan)
        since = now - (st.revealed_at or st.finished_at or now - 9)
        p = ease_out(since / 0.6)
        if since < 0.9:
            q = ease_out(since / 0.9)
            cr.set_source_rgba(*col, 0.35 * (1 - q))
            cr.set_line_width(1 * s)
            cr.new_path()
            cr.arc(x, y, (5 + 9 * q) * s, 0, TAU)
            cr.stroke()
        cr.set_source_rgba(*col, 0.16 * p)
        cr.new_path()
        cr.arc(x, y, 8 * s, 0, TAU)
        cr.fill()
        cr.set_source_rgba(*col, 0.4 + 0.6 * p)
        cr.new_path()
        cr.arc(x, y, 4.2 * s, 0, TAU)
        cr.fill()

    def label(self, cr, W, s, now, st, i, x, y, ang, cx):
        status = status_of(st)
        waiting = st.status == "wait"
        lit = st.revealed_at or (st.finished_at if st.status not in ("wait", "run") else None)
        fade = ease_out((now - lit) / 0.45) if lit is not None else 1.0
        title = st.title
        tcol = FG if not waiting else FAINT
        chip = None
        if st.status == "run" and st.revealed_at is None:
            on_way = st.started_at is not None and now - st.started_at < dm.Pacer.BEAM
            sub, scol, sub_a = ("" if on_way else "Checking…"), self.scan, 0.9
        else:
            sub = self.summary(st) if not waiting else ""
            scol = (0.93, 0.62, 0.62) if status == "red" else SUB
            sub_a = fade
            chip = None if waiting else status
        size = 13 * s
        num = f"{i + 1:02d}"
        nw = self.layout(cr, num, 10.5 * s, MONO).get_pixel_size()[0]
        tw = self.layout(cr, title, size, SANS, "Medium").get_pixel_size()[0]
        cw = self.chip_width(cr, chip, s) if chip else 0
        total = nw + 8 * s + tw + (10 * s + cw if chip else 0)
        if abs(math.cos(ang)) < 0.12:  # the node right at the top or bottom: label over / under it
            above = math.sin(ang) < 0
            ty = y - (46 if sub else 32) * s if above else y + 14 * s
            x0, sx, sal, swidth = x - total / 2, x, "center", 270 * s
        else:
            right = x >= cx
            tx = x + (18 if right else -18) * s
            ty = y - 18 * s
            x0 = tx if right else tx - total
            room = (W - tx if right else tx) - 30 * s
            sx, sal, swidth = tx, "left" if right else "right", max(80 * s, min(300 * s, room))
        self.text(cr, num, x0, ty + 2 * s, 10.5 * s, FAINT, font=MONO)
        self.text(cr, title, x0 + nw + 8 * s, ty, size, tcol, weight="Medium")
        if chip:
            self.chip(cr, chip, x0 + nw + 8 * s + tw + 10 * s, ty + 2 * s, s, alpha=fade)
        if sub:
            self.text(cr, sub, sx, ty + 20 * s + (1 - fade) * 4 * s, 11.5 * s, scol, sub_a, align=sal, width=swidth)

    def summary(self, st):
        if not st.results:
            return "Nothing to check here" if st.status == "na" else ""
        rank = {"red": 0, "yellow": 1, "green": 2, "info": 3, "n/a": 4}
        top = min(st.results, key=lambda r: rank.get(r.get("status"), 5))
        more = f"  +{len(st.results) - 1} more" if len(st.results) > 1 else ""
        text = top.get("summary", "")
        return (text[:1].upper() + text[1:]) + more

    # ------------------------------------------------ the centre

    def palette(self, cr, s, now, cx, cy, waiting):
        """A command palette: what to run."""
        w, rh = 420 * s, 50 * s
        h = 44 * s + rh * len(MENU) + 8 * s
        x, y = cx - w / 2, cy - h / 2 - 10 * s
        self.box(cr, x, y, w, h, fill_a=0.94, line_a=0.10, r=8 * s)
        if waiting:
            spin = SPINNER[int(now * 10) % len(SPINNER)]
            self.text(cr, f"Waiting for your password  {spin}", x + 18 * s, y + 14 * s, 13 * s, FG, weight="Medium")
        else:
            self.text(cr, "Run diagnostics", x + 18 * s, y + 14 * s, 13 * s, FG, weight="Medium")
            self.text(cr, "↑↓  Enter", x + w - 18 * s, y + 15 * s, 11 * s, FAINT, font=MONO, align="right")
        self.hline(cr, x + 1, x + w - 1, y + 42 * s, 0.07)
        yy = y + 46 * s
        for i, (name, dur, _args, desc) in enumerate(MENU):
            sel = i == self.menu_sel and not waiting
            if sel:
                cr.set_source_rgba(*self.accent, 0.12)
                cr.rectangle(x + 6 * s, yy + 2 * s, w - 12 * s, rh - 4 * s)
                cr.fill()
                cr.set_source_rgba(*self.accent, 0.9)
                cr.rectangle(x + 6 * s, yy + 2 * s, 2 * s, rh - 4 * s)
                cr.fill()
            kx, ky = x + 20 * s, yy + 14 * s
            self.box(cr, kx, ky, 20 * s, 20 * s, fill=(0.10, 0.11, 0.13), fill_a=1, line_a=0.16, r=4 * s)
            self.text(cr, str(i + 1), kx + 10 * s, ky + 2.5 * s, 11 * s, FG if sel else SUB, font=MONO, align="center")
            self.text(cr, name, x + 54 * s, yy + 8 * s, 13.5 * s, FG if not waiting else SUB, weight="Medium")
            self.text(cr, desc, x + 54 * s, yy + 27 * s, 11.5 * s, SUB)
            self.text(cr, dur, x + w - 18 * s, yy + 17 * s, 11.5 * s, SUB, font=MONO, align="right")
            if not waiting:
                self.hits.append((x, yy, w, rh, f"menu:{i}"))
            yy += rh
        if self.last:
            st = self.last["overall"]
            word = WORDS.get(st, "")
            ly = y + h + 14 * s
            lead = f"Last check here  ·  {self.last['created'][:16].replace('T', ' ')}  ·  "
            lw = self.layout(cr, lead, 11.5 * s).get_pixel_size()[0]
            ww = self.layout(cr, word, 11.5 * s, SANS, "Medium").get_pixel_size()[0]
            x0 = cx - (lw + 10 * s + ww) / 2
            self.text(cr, lead, x0, ly, 11.5 * s, SUB)
            col = VERDICT.get(st, SUB)
            cr.set_source_rgba(*col, 1)
            cr.new_path()
            cr.arc(x0 + lw + 3.5 * s, ly + 8 * s, 3 * s, 0, TAU)
            cr.fill()
            self.text(cr, word, x0 + lw + 10 * s, ly, 11.5 * s, col, weight="Medium")
            self.hits.append((x0, ly, lw + 10 * s + ww, 18 * s, "last"))

    def ring(self, cr, s, now, run, cx, cy, r, final_from=None):
        """One thin segment per check, in its status colour once checked."""
        stars = run.stars
        n = max(1, len(stars))
        cr.set_line_width(1 * s)
        cr.set_source_rgba(*HAIR, 0.05)
        cr.new_path()
        cr.arc(cx, cy, r + 12 * s, 0, TAU)
        cr.stroke()
        cr.set_source_rgba(*HAIR, 0.14)
        for k in range(n):  # a tick per check, outside
            a = -math.pi / 2 + k * TAU / n
            cr.move_to(cx + (r + 9 * s) * math.cos(a), cy + (r + 9 * s) * math.sin(a))
            cr.line_to(cx + (r + 15 * s) * math.cos(a), cy + (r + 15 * s) * math.sin(a))
        cr.stroke()
        gap = 0.035
        cr.set_line_width(3 * s)
        for i, st in enumerate(stars):
            a0 = -math.pi / 2 + i * TAU / n + gap
            a1 = -math.pi / 2 + (i + 1) * TAU / n - gap
            status = status_of(st)
            alpha = 1.0
            if final_from is not None:
                alpha = ease_out((now - final_from - i * 0.06) / 0.4)
            cr.set_source_rgba(*HAIR, 0.07)
            cr.new_path()
            cr.arc(cx, cy, r, a0, a1)
            cr.stroke()
            if status == "wait":
                continue
            if status == "run":
                col, alpha = self.scan, 0.45 + 0.35 * (0.5 + 0.5 * math.sin(now * 3.5))
            else:
                col = colour(status, self.scan)
            cr.set_source_rgba(*col, alpha)
            cr.new_path()
            cr.arc(cx, cy, r, a0, a1)
            cr.stroke()

    def progress(self, cr, s, now, run, cx, cy):
        r = 96 * s
        self.ring(cr, s, now, run, cx, cy, r)
        pct = f"{int(round(self.shown * 100))}"
        pw = self.layout(cr, pct, 44 * s, MONO, "Light").get_pixel_size()[0]
        uw = self.layout(cr, "%", 16 * s, MONO).get_pixel_size()[0]
        x0 = cx - (pw + 2 * s + uw) / 2
        self.text(cr, pct, x0, cy - 40 * s, 44 * s, FG, font=MONO, weight="Light")
        self.text(cr, "%", x0 + pw + 2 * s, cy - 23 * s, 16 * s, SUB, font=MONO)
        cur = run.star(run.current)
        self.caption(cr, "Checking", cx, cy + 14 * s, s, SUB, align="center")
        self.text(cr, cur.title if cur else "Starting", cx, cy + 30 * s, 13 * s, FG, weight="Medium", align="center",
                  width=150 * s)
        live = run.live
        if run.current == "cpu_load" and live and live.get("t"):
            left = max(0, (live.get("total") or 0) - (live.get("t") or 0))
            clk = f"{live['mhz'] / 1000:.2f} GHz" if live.get("mhz") else "? GHz"
            line = f"{live.get('temp', '?')} °C  ·  {clk}  ·  {left // 60}:{left % 60:02d} left"
            self.text(cr, line, cx, cy + r + 26 * s, 11.5 * s, SUB, font=MONO, align="center")
            self.trace(cr, s, run, cx, cy + r + 50 * s, 260 * s, 34 * s)

    def trace(self, cr, s, run, cx, top, w, h):
        """CPU temperature during the stress test, against the CPU's own limit (dashed)."""
        temps = run.temps[-180:]
        tj = run.live.get("tjmax") or 100
        if len(temps) < 2:
            return
        lo, hi = min(min(temps), 30), max(tj, max(temps))
        x0 = cx - w / 2
        ly = top + h - (tj - lo) / (hi - lo) * h
        cr.set_source_rgba(*VERDICT["red"], 0.5)
        cr.set_line_width(1 * s)
        cr.set_dash([3 * s, 3 * s])
        cr.move_to(x0, ly)
        cr.line_to(x0 + w, ly)
        cr.stroke()
        cr.set_dash([])
        self.hline(cr, x0, x0 + w, top + h, 0.10)
        cr.set_source_rgba(*self.scan, 0.9)
        cr.set_line_width(1.4 * s)
        for i, t in enumerate(temps):
            x = x0 + i / (len(temps) - 1) * w
            y = top + h - (t - lo) / (hi - lo) * h
            (cr.line_to if i else cr.move_to)(x, y)
        cr.stroke()

    def diagnosis(self, cr, s, now, run, cx, cy):
        r = 96 * s
        end = run.ended_at or now
        self.ring(cr, s, now, run, cx, cy, r, final_from=end)
        if run.phase == "done":
            word, col = WORDS.get(run.overall, (run.overall or "").title()), VERDICT.get(run.overall, FG)
        else:
            word, col = ("Stopped" if run.phase == "stopped" else "Incomplete"), SUB
        start = end + 0.06 * len(run.stars) + 0.2
        a = ease_out((now - start) / 0.6)
        self.caption(cr, "Diagnosis", cx, cy - 34 * s, s, SUB, a, align="center")
        self.text(cr, word, cx, cy - 16 * s + (1 - a) * 6 * s, 21 * s, col, a, weight="Semi-Bold", align="center")
        n = sum(1 for st in run.stars if status_of(st) not in ("wait", "run"))
        el = int(end - (run.started_at or end))
        self.text(cr, f"{n} of {len(run.stars)} checks  ·  {el // 60}:{el % 60:02d}", cx, cy + 16 * s, 11.5 * s, SUB, a,
                  font=MONO, align="center")

    # ------------------------------------------------ activity log and actions

    def activity(self, cr, W, H, s, now, run, pad, top, waiting):
        bottom = H - 20 * s
        split = W - pad - 290 * s
        self.box(cr, pad, top, split - pad - 12 * s, bottom - top, fill_a=0.9, line_a=0.08, r=8 * s)
        self.box(cr, split, top, W - pad - split, bottom - top, fill_a=0.9, line_a=0.08, r=8 * s)
        self.caption(cr, "Activity", pad + 18 * s, top + 14 * s, s)
        self.caption(cr, "Actions", split + 18 * s, top + 14 * s, s)
        lh = 20 * s
        rows = max(1, int((bottom - top - 44 * s) / lh))
        lines = list(run.feed)
        mono_now, wall_now = now, time.time()
        if waiting:
            lines.append((waiting, f"{'Password':<15}Waiting for your password {SPINNER[int(now * 10) % len(SPINNER)]}", "run"))
        if not lines:
            lines = [(None, f"{'Ready':<15}Choose a check: keys 1–4, or click", "info")]
        lines = lines[-rows:]
        y = top + 38 * s
        x0 = pad + 18 * s
        for k, (t, msg, status) in enumerate(lines):
            stamp = datetime.datetime.fromtimestamp(wall_now - (mono_now - t)).strftime("%H:%M:%S") if t else "--:--:--"
            newest = k == len(lines) - 1
            a = ease_out((now - t) / 0.35) if (newest and t) else 1.0
            off = (1 - a) * 5 * s
            name, body = msg[:15].strip(), msg[15:]
            self.text(cr, stamp, x0, y + off, 11.5 * s, FAINT, a, font=MONO)
            col = colour(status, self.scan) if status != "info" else INFO
            self.text(cr, CHIP.get(status, ""), x0 + 82 * s, y + off, 11 * s, col, a, font=MONO, weight="Bold")
            self.text(cr, name, x0 + 128 * s, y + off, 11.5 * s, SUB, a, font=MONO)
            self.text(cr, body, x0 + 246 * s, y + off, 11.5 * s, FG if newest else (0.78, 0.79, 0.82), a, font=MONO,
                      width=split - x0 - 270 * s)
            y += lh
        if run.phase == "idle":
            cmds = [("↵", "Start selected check", "cmd:start"), ("R", "Open reports folder", "cmd:reports"),
                    ("Esc", "Close", "cmd:close")]
        elif run.phase == "running":
            cmds = [("S", "Stop safely", "cmd:stop")]
        else:
            cmds = [("O", "Owner summary", "cmd:owner"), ("F", "Full report", "cmd:report"), ("N", "New check", "cmd:new")]
        y = top + 38 * s
        for key, label, action in cmds:
            hov = self.hover == action
            if hov:
                cr.set_source_rgba(*self.accent, 0.12)
                cr.rectangle(split + 8 * s, y - 4 * s, W - pad - split - 16 * s, 28 * s)
                cr.fill()
            kw = max(22 * s, self.layout(cr, key, 11 * s, MONO).get_pixel_size()[0] + 12 * s)
            self.box(cr, split + 18 * s, y, kw, 20 * s, fill=(0.10, 0.11, 0.13), fill_a=1, line_a=0.16, r=4 * s)
            self.text(cr, key, split + 18 * s + kw / 2, y + 2.5 * s, 11 * s, FG, font=MONO, align="center")
            self.text(cr, label, split + 18 * s + kw + 12 * s, y + 1.5 * s, 13 * s, FG if hov else (0.82, 0.83, 0.86))
            self.hits.append((split + 8 * s, y - 4 * s, W - pad - split - 16 * s, 28 * s, action))
            y += 32 * s

    # ------------------------------------------------ a node's findings

    def details(self, cr, W, H, s, run, cx, cy):
        st = run.star(self.detail)
        if not st:
            self.detail = None
            return
        cr.set_source_rgba(*BG, 0.55)
        cr.paint()
        w = 580 * s
        h = (60 + 50 * len(st.results)) * s
        x, y = cx - w / 2, cy - h / 2
        self.box(cr, x, y, w, h, fill_a=0.98, line_a=0.14, r=10 * s)
        self.text(cr, st.title, x + 22 * s, y + 18 * s, 15 * s, FG, weight="Semi-Bold")
        self.chip(cr, status_of(st), x + w - 22 * s, y + 20 * s, s, align="right")
        self.hline(cr, x + 1, x + w - 1, y + 50 * s, 0.07)
        yy = y + 62 * s
        for r in st.results:
            status = (r.get("status") or "info").replace("n/a", "na")
            cr.set_source_rgba(*colour(status, self.scan), 1)
            cr.new_path()
            cr.arc(x + 26 * s, yy + 8 * s, 3 * s, 0, TAU)
            cr.fill()
            self.text(cr, r.get("title", ""), x + 40 * s, yy, 13 * s, FG, weight="Medium", width=w - 70 * s)
            self.text(cr, r.get("summary", ""), x + 40 * s, yy + 19 * s, 12 * s, SUB, width=w - 70 * s)
            yy += 50 * s
        self.hits.append((0, 0, W, H, "detail:close"))
