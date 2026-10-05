"""Chiron Doctor's picture: the star chart in a terminal / HUD style (Tete, 2026-10-05: "I still want
the star chart but in a style of terminal and techy look", with smooth, unhurried animation).

Every check is a node on a wide ellipse. A beam travels along the link to the next node, the node
scans (a rotating reticle), then locks onto its result: the node lights up green, amber or red with a
glitch flash and its label types out, like a line of a boot log. A log panel types each event; the
centre is a terminal menu, then a segmented progress ring, then the diagnosis.

Only cairo and Pango: the window (doctor_window.py) and tools/doctor-frames.py both draw through
Scene.render(). Verdict colours are fixed (CLAUDE.md decision 10); the theme's accent does the rest."""
import colorsys
import datetime
import math
import random
import time

import cairo
import gi

gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Pango, PangoCairo  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter, ImageOps  # noqa: E402

from chiron import doctor_model as dm  # noqa: E402
from chiron.checks import MODULES, TITLES  # noqa: E402

MONO = "JetBrainsMono Nerd Font, JetBrains Mono, DejaVu Sans Mono, monospace"
BG = (0.030, 0.028, 0.055)
FG = (0.86, 0.88, 0.94)
DIM = (0.45, 0.46, 0.57)
FAINT = (0.22, 0.22, 0.31)
VERDICT = {"green": (0.20, 0.83, 0.45), "yellow": (0.98, 0.70, 0.14), "red": (0.97, 0.31, 0.31)}  # fixed
TAG = {"green": "[ OK ]", "yellow": "[WARN]", "red": "[FAIL]", "info": "[INFO]", "na": "[ -- ]",
       "run": "[ .. ]", "wait": "[    ]"}
WORDS = {"green": "ALL GOOD", "yellow": "WORTH A LOOK", "red": "PROBLEM FOUND"}
MENU = [("health check", "~3 min", ["report"]), ("quick check", "~1 min", ["report", "--quick"]),
        ("stress test", "10 min", ["stress"]), ("check + stress", "~13 min", ["full"])]
SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
TAU = 2 * math.pi


def clamp(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, v))


def ease_out(t):
    return 1 - (1 - clamp(t)) ** 3


def ease_in_out(t):
    t = clamp(t)
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def typed(s, since, now, cps=60):
    """The part of s typed so far (since: when typing began), and whether it's all there."""
    if since is None:
        return s, True
    n = int(max(0.0, now - since) * cps)
    return s[:n], n >= len(s)


def cursor_on(now):
    return (now % 1.06) < 0.62


def status_of(st):
    """What a node shows: its final status, its verdict as soon as a finding is in, or run/wait."""
    if st.status not in ("wait", "run"):
        return st.status
    if st.revealed_at is not None:
        return st.verdict
    return st.status


SCAN_CYAN = (0.35, 0.85, 1.0)


def scan_colour(accent):
    """The colour of everything that scans (beam, reticle, links, the running segment): the theme's
    accent unless it could be mistaken for green, amber or red, then a cool cyan."""
    h, l, sat = colorsys.rgb_to_hls(*accent)
    near = min(min(abs(h - v), 1 - abs(h - v)) for v in (0.0, 0.11, 0.39))  # red, amber, green hues
    return accent if near >= 0.1 and sat >= 0.2 else SCAN_CYAN


def colour(status, accent):
    return VERDICT.get(status) or {"run": accent, "info": (0.78, 0.80, 0.90), "na": DIM}.get(status, FAINT)


def surface(im):
    im = im.convert("RGBA")
    w, h = im.size
    return cairo.ImageSurface.create_for_data(bytearray(im.tobytes("raw", "BGRa")), cairo.FORMAT_ARGB32, w, h, w * 4)


def backdrop(wall, w, h):
    """Terminal black with the person's wallpaper faintly under it, a fine grid, scanlines and a
    vignette. Drawn once per window size."""
    base = Image.new("RGB", (w, h), tuple(int(c * 255) for c in BG))
    if wall:
        try:
            with Image.open(wall) as src:
                src.draft("RGB", (w // 4, h // 4))
                im = ImageOps.fit(src.convert("RGB"), (max(64, w // 8), max(36, h // 8)), Image.BILINEAR)
            im = im.filter(ImageFilter.GaussianBlur(2.5)).resize((w, h), Image.BILINEAR)
            base = Image.blend(base, im, 0.16)
        except OSError:
            pass
    over = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    step = max(24, int(48 * min(w / 1280, h / 800)))
    for x in range(0, w, step):
        d.line([(x, 0), (x, h)], fill=(140, 150, 200, 9))
    for y in range(0, h, step):
        d.line([(0, y), (w, y)], fill=(140, 150, 200, 9))
    for y in range(0, h, 3):
        d.line([(0, y), (w, y)], fill=(0, 0, 0, 34))
    base = base.convert("RGBA")
    base.alpha_composite(over)
    # vignette: darker towards the edges
    vg = Image.radial_gradient("L").resize((w, h)).point(lambda v: int(clamp((v - 120) / 135) * 150))
    base = Image.composite(Image.new("RGBA", (w, h), (0, 0, 0, 255)), base, vg)
    rng = random.Random(3)
    d = ImageDraw.Draw(base)
    for _ in range(int(w * h / 9000)):  # a few faint stars: it's still a star chart
        x, y, m = rng.random() * w, rng.random() * h, rng.random() ** 4
        d.point((x, y), fill=(200, 200, 240, int(40 + 120 * m)))
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
        self.shown = 0.0          # progress ring, eased
        self.last_now = None
        self._layouts = {}

    # ------------------------------------------------ text

    def text(self, cr, s, x, y, size, color, alpha=1.0, bold=False, align="left", width=None):
        layout = PangoCairo.create_layout(cr)
        layout.set_font_description(Pango.FontDescription(f"{MONO} {'Bold' if bold else ''} {size:.1f}px"))
        layout.set_text(s, -1)
        if width:
            layout.set_width(int(max(1, width) * Pango.SCALE))
            layout.set_ellipsize(Pango.EllipsizeMode.END)
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

    def glitch(self, cr, s, x, y, size, color, p, bold=True, align="left"):
        """A short chromatic glitch (p: 0..1 through it) under the real text."""
        if p < 1:
            j = (1 - p) * 3.5
            off = math.sin(p * 37) * j
            self.text(cr, s, x + off + j, y, size, (1.0, 0.2, 0.35), 0.55 * (1 - p), bold, align)
            self.text(cr, s, x - off - j, y, size, (0.2, 0.9, 1.0), 0.55 * (1 - p), bold, align)
        self.text(cr, s, x, y, size, color, 1.0, bold, align)

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
        self.shown += (run.progress() - self.shown) * clamp(dt * 4)
        pad = 26 * s
        log_top = H - 158 * s
        top, bottom = 96 * s, log_top - 14 * s
        self.header(cr, W, s, now, run, pad, waiting)
        self.frame(cr, W, s, now, run, pad, top, bottom)
        cx, cy = W / 2, (top + bottom) / 2
        room = 50 * s
        ry = (bottom - top) / 2 - room
        rx = min(W * 0.34, ry * 2.0, W / 2 - pad - 250 * s)
        self.chart(cr, W, s, now, run, cx, cy, rx, ry)
        if run.phase == "idle":
            self.menu(cr, s, now, cx, cy, waiting)
        elif run.phase == "running":
            self.progress(cr, s, now, run, cx, cy)
        else:
            self.diagnosis(cr, s, now, run, cx, cy)
        self.log(cr, W, H, s, now, run, pad, log_top, waiting)
        if self.detail:
            self.details(cr, W, s, run, cx, cy)

    # ------------------------------------------------ header and frame

    def header(self, cr, W, s, now, run, pad, waiting):
        y = 20 * s
        x = pad
        w, _ = self.text(cr, f"{self.user}@chiron", x, y, 17 * s, self.accent, bold=True)
        x += w
        w, _ = self.text(cr, ":~$ ", x, y, 17 * s, FG)
        x += w
        cmd = "chiron doctor"
        if run.phase == "running" or waiting:
            cmd = "chiron doctor --run"
        w, h = self.text(cr, cmd, x, y, 17 * s, FG)
        if cursor_on(now):
            cr.set_source_rgba(*self.accent, 0.9)
            cr.rectangle(x + w + 4 * s, y + 3 * s, 9 * s, h - 6 * s)
            cr.fill()
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.text(cr, f"// pc doctor · {stamp}", pad, y + 28 * s, 12 * s, DIM)
        name = " ".join(v for v in (self.machine.get("sys_vendor"), self.machine.get("product_name")) if v) or "this computer"
        self.text(cr, "TARGET", W - pad, y + 1 * s, 11 * s, DIM, align="right")
        self.text(cr, name.upper(), W - pad, y + 15 * s, 15 * s, FG, bold=True, align="right", width=560 * s)
        self.text(cr, self.spec, W - pad, y + 36 * s, 12 * s, DIM, align="right")
        # rule with a scanner light running along it
        ly = 78 * s
        cr.set_source_rgba(*FAINT, 1)
        cr.set_line_width(1 * s)
        cr.move_to(pad, ly)
        cr.line_to(W - pad, ly)
        cr.stroke()
        for tx in range(int(pad), int(W - pad), int(40 * s)):
            cr.move_to(tx, ly)
            cr.line_to(tx, ly + 4 * s)
        cr.stroke()
        p = (now % 6.0) / 6.0
        hx = pad + (W - 2 * pad) * p
        g = cairo.LinearGradient(hx - 90 * s, 0, hx, 0)
        g.add_color_stop_rgba(0, *self.accent, 0)
        g.add_color_stop_rgba(1, *self.accent, 0.9)
        cr.set_source(g)
        cr.set_line_width(1.6 * s)
        cr.move_to(max(pad, hx - 90 * s), ly)
        cr.line_to(hx, ly)
        cr.stroke()

    def frame(self, cr, W, s, now, run, pad, top, bottom):
        L = 18 * s
        cr.set_source_rgba(*self.accent, 0.55)
        cr.set_line_width(2 * s)
        for (x, y, dx, dy) in ((pad, top, 1, 1), (W - pad, top, -1, 1), (pad, bottom, 1, -1), (W - pad, bottom, -1, -1)):
            cr.move_to(x + dx * L, y)
            cr.line_to(x, y)
            cr.line_to(x, y + dy * L)
        cr.stroke()
        n = len(run.stars) or len(MODULES)
        el = (run.ended_at or now) - run.started_at if run.started_at else 0
        self.text(cr, "RA 05h 35m 17s", pad + 8 * s, top + 8 * s, 10.5 * s, DIM)
        self.text(cr, "DEC −05° 23′ 28″", W - pad - 8 * s, top + 8 * s, 10.5 * s, DIM, align="right")
        self.text(cr, f"NODES {n:02d}", pad + 8 * s, bottom - 22 * s, 10.5 * s, DIM)
        self.text(cr, f"T+{int(el) // 60:02d}:{int(el) % 60:02d}", W - pad - 8 * s, bottom - 22 * s, 10.5 * s, DIM, align="right")

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
            k = 1.0 if i % 2 == 0 else 0.92
            pts.append((cx + rx * k * math.cos(a), cy + ry * k * math.sin(a), a))
        reached = [st.status != "wait" for st in stars]
        lit = [status_of(st) not in ("wait", "run") for st in stars]
        # links: dashed where the beam hasn't been yet, solid behind it, data pulses on finished ones
        for i in range(n):
            j = (i + 1) % n
            (x1, y1, _), (x2, y2, _) = pts[i], pts[j]
            if reached[i] and reached[j] and (j != 0 or run.phase in ("done",)):
                beam_p = 1.0
                if stars[j].status == "run" and stars[j].started_at is not None:
                    beam_p = ease_in_out((now - stars[j].started_at) / dm.Pacer.BEAM)
                if beam_p < 1.0:
                    continue  # drawn as the travelling beam below
                cr.set_source_rgba(*self.scan, 0.45)
                cr.set_line_width(1.6 * s)
                cr.move_to(x1, y1)
                cr.line_to(x2, y2)
                cr.stroke()
                if lit[i] and lit[j]:
                    p = (now * 0.35 + i * 0.37) % 1.0
                    px, py = x1 + (x2 - x1) * p, y1 + (y2 - y1) * p
                    self.dot(cr, px, py, 2.2 * s, self.scan, 0.8)
            else:
                cr.set_source_rgba(*FAINT, 0.9)
                cr.set_line_width(1 * s)
                cr.set_dash([2 * s, 6 * s])
                cr.move_to(x1, y1)
                cr.line_to(x2, y2)
                cr.stroke()
                cr.set_dash([])
        # the beam to the node being checked
        cur = next((i for i, st in enumerate(stars) if st.status == "run"), None)
        if cur is not None and stars[cur].started_at is not None:
            p = ease_in_out((now - stars[cur].started_at) / dm.Pacer.BEAM)
            if p < 1.0:
                sx, sy = (pts[cur - 1][0], pts[cur - 1][1]) if cur > 0 else (cx, cy)
                tx, ty = pts[cur][0], pts[cur][1]
                hx, hy = sx + (tx - sx) * p, sy + (ty - sy) * p
                g = cairo.LinearGradient(sx, sy, hx, hy)
                g.add_color_stop_rgba(0, *self.scan, 0.15)
                g.add_color_stop_rgba(1, *self.scan, 1.0)
                cr.set_source(g)
                cr.set_line_width(2.2 * s)
                cr.move_to(sx, sy)
                cr.line_to(hx, hy)
                cr.stroke()
                self.dot(cr, hx, hy, 3.5 * s, self.scan, 1.0, glow=5)
        for i, (st, (x, y, ang)) in enumerate(zip(stars, pts)):
            self.node(cr, s, now, st, i, x, y)
            self.label(cr, W, s, now, st, i, x, y, ang, cx)
            if st.results:
                self.hits.append((x - 24 * s, y - 24 * s, 48 * s, 48 * s, f"node:{st.id}"))

    def dot(self, cr, x, y, r, col, a, glow=3):
        cr.new_path()
        g = cairo.RadialGradient(x, y, 0, x, y, r * glow)
        g.add_color_stop_rgba(0, *col, 0.6 * a)
        g.add_color_stop_rgba(1, *col, 0)
        cr.set_source(g)
        cr.arc(x, y, r * glow, 0, TAU)
        cr.fill()
        cr.set_source_rgba(*col, a)
        cr.arc(x, y, r, 0, TAU)
        cr.fill()

    def diamond(self, cr, x, y, r):
        cr.new_path()
        cr.move_to(x, y - r)
        cr.line_to(x + r, y)
        cr.line_to(x, y + r)
        cr.line_to(x - r, y)
        cr.close_path()

    def node(self, cr, s, now, st, i, x, y):
        status = status_of(st)
        col = colour(status, self.scan)
        if st.status == "wait":
            cr.set_source_rgba(*FAINT, 1)
            cr.set_line_width(1.2 * s)
            cr.rectangle(x - 3.5 * s, y - 3.5 * s, 7 * s, 7 * s)
            cr.stroke()
            return
        arrived = st.started_at is None or now - st.started_at >= dm.Pacer.BEAM
        if st.status == "run" and not arrived:
            cr.set_source_rgba(*self.scan, 0.5)
            cr.set_line_width(1.4 * s)
            self.diamond(cr, x, y, 6 * s)
            cr.stroke()
            return
        scanning = st.status == "run" and st.revealed_at is None
        lock = None if scanning else clamp((now - (st.revealed_at or st.finished_at or now)) / 0.45)
        # reticle: rotates while scanning, closes in on the node as it locks
        if scanning or (lock is not None and lock < 1):
            rot = now * 1.8
            rr = (17 + 2.5 * math.sin(now * 5)) * s if scanning else (17 - 9 * ease_out(lock)) * s
            a = 0.95 if scanning else 0.95 * (1 - lock)
            cr.set_source_rgba(*self.scan, a)
            cr.set_line_width(1.8 * s)
            for q in range(4):
                ang = rot + q * TAU / 4
                cr.new_path()
                cr.arc(x, y, rr, ang - 0.32, ang + 0.32)
                cr.stroke()
            if scanning:
                cr.set_line_width(1 * s)
                cr.set_source_rgba(*self.scan, 0.45)
                cr.set_dash([3 * s, 4 * s])
                cr.new_path()
                cr.arc(x, y, 25 * s, -now * 1.2, -now * 1.2 + TAU * 0.7)
                cr.stroke()
                cr.set_dash([])
                # sweep line
                sa = now * 3.2
                g = cairo.RadialGradient(x, y, 0, x, y, 25 * s)
                g.add_color_stop_rgba(0, *self.scan, 0.35)
                g.add_color_stop_rgba(1, *self.scan, 0)
                cr.set_source(g)
                cr.move_to(x, y)
                cr.arc(x, y, 25 * s, sa - 0.5, sa)
                cr.close_path()
                cr.fill()
                pulse = 0.5 + 0.5 * math.sin(now * 6)
                cr.set_source_rgba(*self.scan, 0.5 + 0.4 * pulse)
                self.diamond(cr, x, y, 5 * s)
                cr.fill()
                return
        # locked: a lit diamond in its verdict colour, a burst when it has just locked
        since = now - (st.revealed_at or st.finished_at or now - 9)
        if since < 1.0:
            p = ease_out(since / 1.0)
            cr.set_source_rgba(*col, 0.7 * (1 - p))
            cr.set_line_width(2.5 * s * (1 - p) + 0.5)
            cr.new_path()
            cr.arc(x, y, (9 + 34 * p) * s, 0, TAU)
            cr.stroke()
        r = 8 * s * (1 + 0.35 * max(0.0, 1 - since / 0.35))
        g = cairo.RadialGradient(x, y, 0, x, y, r * 3.4)
        g.add_color_stop_rgba(0, *col, 0.55)
        g.add_color_stop_rgba(1, *col, 0)
        cr.set_source(g)
        cr.new_path()
        cr.arc(x, y, r * 3.4, 0, TAU)
        cr.fill()
        cr.set_source_rgba(*col, 1)
        self.diamond(cr, x, y, r)
        cr.fill()
        cr.set_source_rgba(1, 1, 1, 0.85)
        self.diamond(cr, x, y, r * 0.38)
        cr.fill()

    def spans(self, cr, parts, x, y, size, align="left", glitch_p=1.0):
        """Draw (text, colour, bold) pieces on one line, aligned as a whole. The pieces marked
        bold glitch while glitch_p < 1 (a node that has just locked)."""
        widths = []
        for t, _c, b in parts:
            layout = PangoCairo.create_layout(cr)
            layout.set_font_description(Pango.FontDescription(f"{MONO} {'Bold' if b else ''} {size:.1f}px"))
            layout.set_text(t, -1)
            widths.append(layout.get_pixel_size()[0])
        total = sum(widths)
        x0 = x - (total / 2 if align == "center" else total if align == "right" else 0)
        for (t, c, b), w in zip(parts, widths):
            if b and glitch_p < 1:
                self.glitch(cr, t, x0, y, size, c, glitch_p, bold=True)
            else:
                self.text(cr, t, x0, y, size, c, bold=b)
            x0 += w
        return total

    def label(self, cr, W, s, now, st, i, x, y, ang, cx):
        status = status_of(st)
        col = colour(status, self.scan)
        locked_at = st.revealed_at or (st.finished_at if st.status not in ("wait", "run") else None)
        scanning = st.status == "run" and st.revealed_at is None and st.started_at is not None
        if scanning and now - st.started_at < dm.Pacer.BEAM:
            sub = "linking"   # the beam is still on its way
        elif scanning:
            sub = "scanning" + "." * (int(now * 3) % 4)
        elif locked_at is not None:
            sub, _ = typed(self.summary(st), locked_at + 0.15, now, cps=70)
        else:
            sub = ""
        tcol = FG if st.status != "wait" else DIM
        scol = VERDICT.get(status) if status in ("yellow", "red") else DIM
        gp = clamp((now - locked_at) / 0.3) if locked_at is not None else 1.0
        num, title = (f"{i + 1:02d}", DIM, False), (st.title.upper(), tcol, True)
        tag = (TAG.get(status, ""), col, False) if st.status != "wait" else ("", FAINT, False)
        size = 13.5 * s
        if abs(math.cos(ang)) < 0.12:  # the node right at the top or bottom: label over / under it
            above = math.sin(ang) < 0
            ty = y - (48 if sub else 34) * s if above else y + 16 * s
            self.spans(cr, [num, (" ", FG, False), title, (" ", FG, False), tag], x, ty, size, "center", gp)
            if sub:
                self.text(cr, sub, x, ty + 19 * s, 11.5 * s, scol, align="center", width=260 * s)
        else:
            right = x >= cx
            tx = x + (22 if right else -22) * s
            parts = [num, (" ", FG, False), title, (" ", FG, False), tag]
            self.spans(cr, parts, tx, y - 18 * s, size, "left" if right else "right", gp)
            if sub:
                room = (W - tx if right else tx) - 28 * s
                self.text(cr, sub, tx, y + 1 * s, 11.5 * s, scol, align="left" if right else "right",
                          width=max(80 * s, min(300 * s, room)))

    def summary(self, st):
        if not st.results:
            return "nothing to check here" if st.status == "na" else ""
        rank = {"red": 0, "yellow": 1, "green": 2, "info": 3, "n/a": 4}
        top = min(st.results, key=lambda r: rank.get(r.get("status"), 5))
        more = f"  (+{len(st.results) - 1})" if len(st.results) > 1 else ""
        return f"{top.get('summary', '')}{more}"

    # ------------------------------------------------ the centre

    def menu(self, cr, s, now, cx, cy, waiting):
        w, rh = 380 * s, 34 * s
        h = 34 * s + rh * len(MENU) + 14 * s
        x, y = cx - w / 2, cy - h / 2 - 12 * s
        cr.set_source_rgba(0.02, 0.02, 0.04, 0.82)
        cr.rectangle(x, y, w, h)
        cr.fill()
        cr.set_source_rgba(*self.accent, 0.6)
        cr.set_line_width(1.2 * s)
        cr.rectangle(x, y, w, h)
        cr.stroke()
        if waiting:
            spin = SPINNER[int(now * 12) % len(SPINNER)]
            self.text(cr, f"> authenticating {spin}", x + 16 * s, y + 10 * s, 14 * s, self.accent, bold=True)
        else:
            self.text(cr, "> select diagnostic", x + 16 * s, y + 10 * s, 14 * s, self.accent, bold=True)
        yy = y + 38 * s
        for i, (name, dur, _args) in enumerate(MENU):
            sel = i == self.menu_sel
            if sel:
                cr.set_source_rgba(*self.accent, 0.22 if not waiting else 0.1)
                cr.rectangle(x + 8 * s, yy - 2 * s, w - 16 * s, rh - 4 * s)
                cr.fill()
                self.text(cr, "▶", x + 14 * s, yy + 4 * s, 13 * s, self.accent)
            col = FG if sel else DIM
            self.text(cr, f"[{i + 1}] {name}", x + 36 * s, yy + 4 * s, 14 * s, col, bold=sel)
            self.text(cr, dur, x + w - 16 * s, yy + 4 * s, 13 * s, col, align="right")
            if not waiting:
                self.hits.append((x, yy - 2 * s, w, rh, f"menu:{i}"))
            yy += rh
        if self.last:
            word = {"green": "[ OK ] all good", "yellow": "[WARN] worth a look", "red": "[FAIL] problem found"}.get(self.last["overall"], "")
            msg = f"last scan {self.last['created'][:16].replace('T', ' ')}  {word}"
            col = VERDICT.get(self.last["overall"], DIM)
            tw, th = self.text(cr, msg, cx, y + h + 12 * s, 12 * s, col, align="center")
            self.hits.append((cx - tw / 2, y + h + 12 * s, tw, th, "last"))

    def ring(self, cr, s, now, run, cx, cy, r, final_from=None):
        stars = run.stars
        n = max(1, len(stars))
        # outer tick ring, turning slowly
        cr.set_source_rgba(*FAINT, 1)
        cr.set_line_width(1 * s)
        rot = now * 0.12
        for k in range(72):
            a = rot + k * TAU / 72
            l = 7 * s if k % 6 == 0 else 3.5 * s
            cr.move_to(cx + (r + 16 * s) * math.cos(a), cy + (r + 16 * s) * math.sin(a))
            cr.line_to(cx + (r + 16 * s + l) * math.cos(a), cy + (r + 16 * s + l) * math.sin(a))
        cr.stroke()
        gap = 0.045
        for i, st in enumerate(stars):
            a0 = -math.pi / 2 + i * TAU / n + gap
            a1 = -math.pi / 2 + (i + 1) * TAU / n - gap
            status = status_of(st)
            if final_from is not None:
                on = now >= final_from + i * 0.07
                status = status if on else "wait"
            if status == "run":
                col, a = self.scan, 0.45 + 0.4 * math.sin(now * 5) ** 2
            elif status == "wait":
                col, a = (1, 1, 1), 0.07
            else:
                col, a = colour(status, self.scan), 0.95
            if status not in ("wait",):
                cr.set_source_rgba(*col, a * 0.25)
                cr.set_line_width(20 * s)
                cr.new_path()
                cr.arc(cx, cy, r, a0, a1)
                cr.stroke()
            cr.set_source_rgba(*col, a)
            cr.set_line_width(9 * s)
            cr.new_path()
            cr.arc(cx, cy, r, a0, a1)
            cr.stroke()

    def progress(self, cr, s, now, run, cx, cy):
        r = 100 * s
        self.ring(cr, s, now, run, cx, cy, r)
        pct = int(round(self.shown * 100))
        self.text(cr, f"{pct:03d}%", cx, cy - 40 * s, 40 * s, FG, bold=True, align="center")
        cur = run.star(run.current)
        label = f"> {cur.title.lower()}" if cur else "> starting"
        w, h = self.text(cr, label, cx, cy + 10 * s, 13 * s, self.scan, align="center")
        if cursor_on(now):
            cr.set_source_rgba(*self.scan, 0.9)
            cr.rectangle(cx + w / 2 + 3 * s, cy + 12 * s, 7 * s, h - 4 * s)
            cr.fill()
        live = run.live
        if run.current == "cpu_load" and live and live.get("t"):
            left = max(0, (live.get("total") or 0) - (live.get("t") or 0))
            self.text(cr, f"TEMP {live.get('temp', '?')}°C/{live.get('tjmax') or '?'}", cx, cy + 32 * s, 11.5 * s, FG, align="center")
            clk = f"CLK {live['mhz'] / 1000:.2f}GHz" if live.get("mhz") else "CLK ?"
            self.text(cr, f"{clk}  T-{left // 60:02d}:{left % 60:02d}", cx, cy + 48 * s, 11.5 * s, DIM, align="center")
            self.trace(cr, s, run, cx, cy + r + 34 * s, 240 * s, 38 * s)

    def trace(self, cr, s, run, cx, top, w, h):
        temps = run.temps[-180:]
        tj = run.live.get("tjmax") or 100
        if len(temps) < 2:
            return
        lo, hi = min(min(temps), 30), max(tj, max(temps))
        x0 = cx - w / 2
        cr.set_source_rgba(0.02, 0.02, 0.04, 0.8)
        cr.rectangle(x0 - 6 * s, top - 6 * s, w + 12 * s, h + 12 * s)
        cr.fill()
        cr.set_source_rgba(*FAINT, 1)
        cr.set_line_width(1 * s)
        cr.rectangle(x0 - 6 * s, top - 6 * s, w + 12 * s, h + 12 * s)
        cr.stroke()
        ly = top + h - (tj - lo) / (hi - lo) * h
        cr.set_source_rgba(*VERDICT["red"], 0.55)
        cr.set_dash([3 * s, 3 * s])
        cr.move_to(x0, ly)
        cr.line_to(x0 + w, ly)
        cr.stroke()
        cr.set_dash([])
        cr.set_source_rgba(*self.accent, 1)
        cr.set_line_width(1.8 * s)
        for i, t in enumerate(temps):
            x = x0 + i / (len(temps) - 1) * w
            y = top + h - (t - lo) / (hi - lo) * h
            (cr.line_to if i else cr.move_to)(x, y)
        cr.stroke()

    def diagnosis(self, cr, s, now, run, cx, cy):
        r = 100 * s
        end = run.ended_at or now
        self.ring(cr, s, now, run, cx, cy, r, final_from=end)
        if run.phase == "done":
            word, col = WORDS.get(run.overall, (run.overall or "").upper()), VERDICT.get(run.overall, FG)
        else:
            word, col = ("STOPPED" if run.phase == "stopped" else "INCOMPLETE"), DIM
        self.text(cr, "DIAGNOSIS", cx, cy - 34 * s, 11.5 * s, DIM, align="center")
        start = end + 0.07 * len(run.stars) + 0.2
        shown, done = typed(word, start, now, cps=16)
        if shown:
            self.glitch(cr, shown, cx, cy - 14 * s, 22 * s if len(word) > 10 else 26 * s, col, clamp((now - start) / 0.6), align="center")
        n = sum(1 for st in run.stars if status_of(st) not in ("wait", "run"))
        el = int(end - (run.started_at or end))
        self.text(cr, f"{n}/{len(run.stars)} checks · {el // 60}:{el % 60:02d}", cx, cy + 22 * s, 11.5 * s, DIM, align="center")

    # ------------------------------------------------ the log panel

    def log(self, cr, W, H, s, now, run, pad, top, waiting):
        x0, x1, bottom = pad, W - pad, H - 18 * s
        split = x1 - 300 * s
        cr.set_source_rgba(0.015, 0.015, 0.03, 0.88)
        cr.rectangle(x0, top, x1 - x0, bottom - top)
        cr.fill()
        cr.set_source_rgba(*FAINT, 1)
        cr.set_line_width(1 * s)
        cr.rectangle(x0, top, x1 - x0, bottom - top)
        cr.stroke()
        cr.move_to(split, top + 10 * s)
        cr.line_to(split, bottom - 10 * s)
        cr.stroke()
        # title tabs on the border
        for tx, title in ((x0 + 14 * s, " LOG "), (split + 14 * s, " COMMANDS ")):
            w, h = self.text(cr, title, tx, top - 8 * s, 11 * s, BG, 0)
            cr.set_source_rgba(0.015, 0.015, 0.03, 1)
            cr.rectangle(tx, top - 1 * s, w, 2 * s)
            cr.fill()
            self.text(cr, title, tx, top - 8 * s, 11 * s, self.accent, bold=True)
        lh = 19 * s
        rows = max(1, int((bottom - top - 22 * s) / lh))
        lines = list(run.feed)
        mono_now, wall_now = now, time.time()
        if waiting:
            lines.append((waiting, "auth           waiting for your password " + SPINNER[int(now * 12) % len(SPINNER)], "run"))
        if not lines:
            lines = [(None, "ready. pick a diagnostic: [1]-[4] or click", "info")]
        lines = lines[-rows:]
        y = top + 12 * s
        for k, (t, msg, status) in enumerate(lines):
            stamp = datetime.datetime.fromtimestamp(wall_now - (mono_now - t)).strftime("%H:%M:%S") if t else "--:--:--"
            newest = k == len(lines) - 1
            shown, done = typed(msg, t, now, cps=90) if (newest and t) else (msg, True)
            self.text(cr, stamp, x0 + 14 * s, y, 12 * s, DIM)
            tag = TAG.get(status, "[    ]")
            self.text(cr, tag, x0 + 104 * s, y, 12 * s, colour(status, self.scan) if status != "info" else FG, bold=True)
            w, h = self.text(cr, shown, x0 + 162 * s, y, 12 * s, FG if newest else (0.70, 0.72, 0.80), width=split - x0 - 180 * s)
            if newest and cursor_on(now):
                cr.set_source_rgba(*self.accent, 0.9)
                cr.rectangle(x0 + 162 * s + w + 3 * s, y + 2 * s, 7 * s, h - 3 * s)
                cr.fill()
            y += lh
        # commands
        if run.phase == "idle":
            cmds = [("ENTER", "start", "cmd:start"), ("R", "reports", "cmd:reports"), ("ESC", "close", "cmd:close")]
        elif run.phase == "running":
            cmds = [("S", "stop safely", "cmd:stop")]
        else:
            cmds = [("O", "owner summary", "cmd:owner"), ("F", "full report", "cmd:report"), ("N", "new check", "cmd:new")]
        y = top + 12 * s
        for key, label, action in cmds:
            hov = self.hover == action
            if hov:
                cr.set_source_rgba(*self.accent, 0.2)
                cr.rectangle(split + 10 * s, y - 3 * s, x1 - split - 20 * s, 24 * s)
                cr.fill()
            w, _ = self.text(cr, f"[{key}]", split + 20 * s, y, 13 * s, self.accent, bold=True)
            self.text(cr, label, split + 20 * s + max(w, 64 * s) + 8 * s, y, 13 * s, FG if hov else (0.78, 0.80, 0.88))
            self.hits.append((split + 10 * s, y - 3 * s, x1 - split - 20 * s, 24 * s, action))
            y += 28 * s

    # ------------------------------------------------ a node's findings

    def details(self, cr, W, s, run, cx, cy):
        st = run.star(self.detail)
        if not st:
            self.detail = None
            return
        w = 560 * s
        h = (52 + 44 * len(st.results)) * s
        x, y = cx - w / 2, cy - h / 2
        cr.set_source_rgba(0.02, 0.02, 0.04, 0.96)
        cr.rectangle(x, y, w, h)
        cr.fill()
        cr.set_source_rgba(*colour(status_of(st), self.accent), 0.9)
        cr.set_line_width(1.4 * s)
        cr.rectangle(x, y, w, h)
        cr.stroke()
        self.text(cr, f"── {st.title.upper()} ──", x + 16 * s, y + 12 * s, 14 * s, FG, bold=True)
        yy = y + 42 * s
        for r in st.results:
            status = (r.get("status") or "info").replace("n/a", "na")
            self.text(cr, TAG.get(status, "[    ]"), x + 16 * s, yy, 12.5 * s, colour(status, self.accent), bold=True)
            self.text(cr, r.get("title", ""), x + 80 * s, yy, 12.5 * s, FG, bold=True, width=w - 100 * s)
            self.text(cr, r.get("summary", ""), x + 80 * s, yy + 18 * s, 12 * s, DIM, width=w - 100 * s)
            yy += 44 * s
        self.hits.append((0, 0, W, 10_000, "detail:close"))
