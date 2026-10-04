"""The doctor launcher's window (chiron/doctor.py explains the design). GTK 3 + cairo."""
import datetime
import json
import math
import random
import subprocess
import time
from pathlib import Path

import cairo
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gdk, GLib, Gtk, Pango, PangoCairo  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter, ImageOps  # noqa: E402

from chiron import doctor_model as dm  # noqa: E402
from chiron.doctor import (ACTIONS, CHIRON, FG, FONT, LOG, MODULES, MONO, MUTED, RICE, REPORTS, TITLES, VERDICT,  # noqa: E402
                           WAIT, WORDS, colour, greeting, load_module, personal, this_machine)

TAU = 2 * math.pi


# ---------------------------------------------------------------- drawing helpers

def surface(im):
    """PIL image -> cairo surface (premultiplied BGRA on little-endian PCs)."""
    im = im.convert("RGBA")
    w, h = im.size
    return cairo.ImageSurface.create_for_data(bytearray(im.tobytes("raw", "BGRa")), cairo.FORMAT_ARGB32, w, h, w * 4)


def backdrop(wall, w, h):
    """The person's wallpaper turned into a night sky: blurred, darkened, with a fixed star field."""
    sky_top, sky_bottom = (11, 10, 18), (24, 18, 40)
    im = None
    if wall:
        try:
            with Image.open(wall) as src:
                src.draft("RGB", (w // 4, h // 4))
                im = ImageOps.fit(src.convert("RGB"), (max(64, w // 6), max(36, h // 6)), Image.BILINEAR)
            im = im.filter(ImageFilter.GaussianBlur(3)).resize((w, h), Image.BILINEAR)
            im = Image.blend(im, Image.new("RGB", (w, h), sky_top), 0.72)
        except OSError:
            im = None
    if im is None:
        im = Image.new("RGB", (w, h), sky_top)
    grad = Image.linear_gradient("L").resize((w, h))
    im = Image.composite(Image.new("RGB", (w, h), sky_bottom), im, grad.point(lambda v: v * 0.35))
    stars = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(stars)
    rng = random.Random(7)
    for _ in range(int(w * h / 3800)):
        x, y, m = rng.random() * w, rng.random() * h, rng.random() ** 3
        r = 0.5 + 1.3 * m
        d.ellipse([x - r, y - r, x + r, y + r], fill=(235, 230, 255, int(50 + 160 * m)))
    im = im.convert("RGBA")
    im.alpha_composite(stars.filter(ImageFilter.GaussianBlur(1.6)))
    im.alpha_composite(stars)
    return surface(im)


def logo_surface(size):
    try:
        ma = load_module("chiron_assets", RICE / "branding" / "make-assets.py")
        return surface(ma.constellation(size))
    except Exception:  # noqa: BLE001 - no logo is no reason not to open
        return None


def text(cr, s, x, y, size, color, alpha=1.0, weight="", font=FONT, align="left", width=None, wrap=False):
    layout = PangoCairo.create_layout(cr)
    layout.set_font_description(Pango.FontDescription(f"{font} {weight} {size:.1f}px"))
    layout.set_text(s, -1)
    if width:
        layout.set_width(int(width * Pango.SCALE))
        if wrap:
            layout.set_wrap(Pango.WrapMode.WORD_CHAR)
        else:
            layout.set_ellipsize(Pango.EllipsizeMode.END)
    w, h = layout.get_pixel_size()
    if align == "center":
        x -= w / 2
    elif align == "right":
        x -= w
    cr.set_source_rgba(*color, alpha)
    cr.move_to(x, y)
    PangoCairo.show_layout(cr, layout)
    return w, h


def rrect(cr, x, y, w, h, r):
    r = max(0.0, min(r, w / 2, h / 2))
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


def glow_dot(cr, x, y, rad, col, glow=0.55, core=True):
    cr.new_path()
    g = cairo.RadialGradient(x, y, 0, x, y, rad * 3.2)
    g.add_color_stop_rgba(0, *col, glow)
    g.add_color_stop_rgba(1, *col, 0)
    cr.set_source(g)
    cr.arc(x, y, rad * 3.2, 0, TAU)
    cr.fill()
    cr.set_source_rgb(*col)
    cr.arc(x, y, rad, 0, TAU)
    cr.fill()
    if core:
        cr.set_source_rgba(1, 1, 1, 0.9)
        cr.arc(x, y, rad * 0.45, 0, TAU)
        cr.fill()


def ease_out(t):
    return 1 - (1 - min(max(t, 0.0), 1.0)) ** 3


def duration(seconds):
    m, s = divmod(int(seconds), 60)
    return f"{m} min {s} s" if m else f"{s} s"


# ---------------------------------------------------------------- the window

class Doctor(Gtk.Window):
    def __init__(self, demo):
        super().__init__(title="Chiron Doctor")
        self.demo = demo
        self.set_default_size(1280, 800)
        self.set_icon_name("chiron")
        self.maximize()
        self.wall, self.accent = personal()
        self.machine, self.spec = this_machine()
        self.last = dm.last_check(REPORTS, self.machine)
        self.logo = logo_surface(52)
        self.run = dm.Run()
        self.proc = self.waiting = None
        self.bg = self.bg_size = None
        self.hits, self.mouse, self.hover = [], (-1, -1), None
        self.detail = None
        self.toast, self.toast_until = None, 0.0
        self.shown = 0.0          # the progress ring, eased toward the real progress
        self.last_draw = 0.0
        self.tick_id = None
        area = Gtk.DrawingArea()
        area.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.POINTER_MOTION_MASK)
        area.connect("draw", self.on_draw)
        area.connect("button-press-event", self.on_click)
        area.connect("motion-notify-event", self.on_motion)
        self.add(area)
        self.area = area
        self.connect("key-press-event", self.on_key)
        self.connect("destroy", self.on_destroy)

    # ------------------------------------------------ running chiron

    def start(self, args):
        if self.proc:
            return
        self.detail = None
        if self.demo:
            self.play(dm.demo_events())
            return
        LOG.parent.mkdir(parents=True, exist_ok=True)
        log = open(LOG, "a")
        log.write(f"\n=== {datetime.datetime.now():%Y-%m-%d %H:%M:%S} chiron {' '.join(args)}\n")
        log.flush()
        try:
            self.proc = subprocess.Popen(["pkexec", CHIRON, "--events", *args], stdin=subprocess.PIPE,
                                         stdout=subprocess.PIPE, stderr=log, text=True, bufsize=1)
        except OSError as err:
            self.say(f"Can't start chiron: {err}", 6)
            return
        finally:
            log.close()
        self.waiting = time.monotonic()
        self.say("Waiting for your password…", 30)
        GLib.io_add_watch(self.proc.stdout.fileno(), GLib.PRIORITY_DEFAULT,
                          GLib.IOCondition.IN | GLib.IOCondition.HUP, self.on_output)

    def on_output(self, _fd, _cond):
        line = self.proc.stdout.readline() if self.proc else ""
        if line:
            try:
                e = json.loads(line)
            except ValueError:
                return True
            if e.get("e") == "start":
                self.waiting, self.toast = None, None
                self.shown = 0.0
            self.run.apply(e, time.monotonic())
            self.animate()
            return True
        rc = self.proc.wait() if self.proc else 0
        self.proc, self.waiting = None, None
        if self.run.phase == "idle":
            self.say("Cancelled." if rc in (126, 127) else f"chiron couldn't start (exit {rc}): see {LOG}", 6)
        elif self.run.phase == "running":
            self.run.phase = "failed"
            self.say(f"chiron stopped unexpectedly (exit {rc}): see {LOG}", 10)
        self.animate()
        return False

    def stop(self):
        if self.demo and self.run.phase == "running":
            self.run.apply({"e": "stopped"}, time.monotonic())
            self.demo_iter = None
        elif self.proc:
            try:
                self.proc.stdin.write("stop\n")
                self.proc.stdin.flush()
            except OSError:
                pass
            self.say("Stopping safely…", 15)
        self.animate()

    def play(self, events):
        """--demo: a scripted run, no root."""
        self.demo_iter = iter(events)

        def step():
            if self.demo_iter is None:
                return
            try:
                delay, e = next(self.demo_iter)
            except StopIteration:
                return

            def fire():
                if self.demo_iter is not None:
                    self.feed(e)
                    step()
                return False  # one-shot timeout
            GLib.timeout_add(int(delay * 1000), fire)
        step()

    def feed(self, e):
        if e.get("e") == "start":
            self.shown = 0.0
        self.run.apply(e, time.monotonic())
        self.animate()

    def open_file(self, path):
        if path and Path(path).exists():
            subprocess.Popen(["xdg-open", str(path)], start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            self.say("Nothing there yet." if not self.demo else "The demo doesn't write a report.", 4)

    def new_check(self):
        self.run = dm.Run()
        self.last = dm.last_check(REPORTS, self.machine)
        self.detail = None
        self.animate()

    def say(self, msg, seconds):
        self.toast, self.toast_until = msg, time.monotonic() + seconds
        self.animate()

    # ------------------------------------------------ animation

    def busy(self, now):
        recent = any(s.finished_at and now - s.finished_at < 1.2 for s in self.run.stars)
        return (self.run.phase == "running" or recent or self.toast_until > now or self.waiting
                or abs(self.shown - self.run.progress()) > 0.002)

    def animate(self):
        self.area.queue_draw()
        if not self.tick_id:
            self.tick_id = self.add_tick_callback(self.tick)

    def tick(self, _w, _clock):
        now = time.monotonic()
        if not self.busy(now):
            self.tick_id = None
            self.area.queue_draw()
            return False
        # under a stress test: a few frames a second, so the window doesn't take CPU from the test
        if now - self.last_draw >= (0.25 if self.run.under_load() else 1 / 30):
            self.area.queue_draw()
        return True

    # ------------------------------------------------ input

    def on_click(self, _w, ev):
        if self.detail:
            self.detail = None
            self.animate()
            return True
        for x, y, w, h, action, _key in reversed(self.hits):
            if x <= ev.x <= x + w and y <= ev.y <= y + h:
                action()
                self.animate()
                return True
        return True

    def on_motion(self, _w, ev):
        self.mouse = (ev.x, ev.y)
        hover = next((key for x, y, w, h, _a, key in reversed(self.hits) if x <= ev.x <= x + w and y <= ev.y <= y + h), None)
        if hover != self.hover:
            self.hover = hover
            win = self.area.get_window()
            if win:
                win.set_cursor(Gdk.Cursor.new_from_name(self.get_display(), "pointer") if hover else None)
            self.area.queue_draw()
        return True

    def on_key(self, _w, ev):
        name = Gdk.keyval_name(ev.keyval)
        if name == "Escape":
            if self.detail:
                self.detail = None
            elif self.run.phase in ("done", "stopped", "failed"):
                self.new_check()
            elif self.run.phase == "idle" and not self.proc:
                self.destroy()
            self.animate()
        elif name in ("q", "w") and ev.state & Gdk.ModifierType.CONTROL_MASK:
            self.destroy()
        elif name == "Return" and self.run.phase == "idle":
            self.start(ACTIONS[0][2])
        return True

    def on_destroy(self, *_a):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.stdin.close()  # end of input: chiron stops the run safely (events.watch_stop)
            except OSError:
                pass
        Gtk.main_quit()

    # ------------------------------------------------ drawing

    def stars(self):
        """The stars to draw: the run's steps, or (before a run) the report's checks, waiting."""
        if self.run.stars:
            return self.run.stars
        out = []
        for m in MODULES:
            s = dm.Star(m, TITLES[m])
            out.append(s)
        return out

    def on_draw(self, widget, cr):
        now = time.monotonic()
        dt = min(0.2, now - self.last_draw) if self.last_draw else 0.0
        self.last_draw = now
        W, H = widget.get_allocated_width(), widget.get_allocated_height()
        s = max(0.6, min(W / 1280, H / 800))
        if self.bg_size != (W, H):
            self.bg, self.bg_size = backdrop(self.wall, W, H), (W, H)
        cr.set_source_surface(self.bg, 0, 0)
        cr.paint()
        self.hits = []
        target = self.run.progress()
        self.shown += (target - self.shown) * min(1.0, dt * 5)
        self.draw_header(cr, W, s, now)
        geo = self.draw_chart(cr, W, H, s, now)
        cx, cy = geo
        if self.run.phase == "idle":
            self.draw_home(cr, W, H, s, cx, cy)
        elif self.run.phase == "running":
            self.draw_running(cr, W, H, s, cx, cy, now)
        else:
            self.draw_done(cr, W, H, s, cx, cy)
        if self.detail:
            self.draw_detail(cr, W, H, s, cx, cy)
        if self.toast and self.toast_until > now:
            a = min(1.0, (self.toast_until - now) * 2)
            text(cr, self.toast, W / 2, H - 100 * s, 15 * s, FG, a, align="center")
        return True

    def draw_header(self, cr, W, s, now):
        x0, y0 = 30 * s, 22 * s
        if self.logo:
            cr.save()
            cr.translate(x0, y0)
            sc = 52 * s / self.logo.get_width()
            cr.scale(sc, sc)
            cr.set_source_surface(self.logo, 0, 0)
            cr.paint()
            cr.restore()
        text(cr, "CHIRON", x0 + 64 * s, y0 + 2 * s, 23 * s, FG, weight="Bold")
        text(cr, greeting(), x0 + 64 * s, y0 + 32 * s, 15 * s, self.accent)
        name = " ".join(x for x in (self.machine.get("sys_vendor"), self.machine.get("product_name")) if x) or "This computer"
        text(cr, name, W - 30 * s, y0 + 4 * s, 17 * s, FG, align="right", width=520 * s)
        if self.run.phase == "running" and self.run.started_at:
            sub = f"running · {duration(now - self.run.started_at)}"
        elif self.run.phase in ("done", "stopped") and self.run.started_at:
            sub = f"took {duration((self.run.ended_at or now) - self.run.started_at)}"
        else:
            sub = self.spec
        text(cr, sub, W - 30 * s, y0 + 30 * s, 13.5 * s, MUTED, align="right")

    def positions(self, n, cx, cy, rx, ry):
        """Stars on a wide ellipse (screens are wide), every other one a little inside, like a
        constellation rather than a clock face. (x, y, angle) each."""
        pts = []
        for i in range(n):
            a = -math.pi / 2 + i * TAU / n
            k = 1.0 if i % 2 == 0 else 0.9
            pts.append((cx + rx * k * math.cos(a), cy + ry * k * math.sin(a), a))
        return pts

    def draw_chart(self, cr, W, H, s, now):
        stars = self.stars()
        cx, cy = W / 2, H * 0.52
        ry = H * 0.29
        rx = min(W * 0.34, ry * 1.75)
        pts = self.positions(len(stars), cx, cy, rx, ry)
        idle = self.run.phase == "idle"
        finished = [st.status not in ("wait", "run") for st in stars]
        # constellation lines
        cr.set_line_width(1.6 * s)
        for i in range(len(stars)):
            j = (i + 1) % len(stars)
            on = finished[i] and finished[j]
            cr.set_source_rgba(*self.accent, 0.55 if on else 0.16 if idle else 0.12)
            cr.move_to(*pts[i][:2])
            cr.line_to(*pts[j][:2])
            cr.stroke()
        gap = rx * TAU / len(stars) * 0.9  # room for a label under or over a star
        for st, (x, y, ang) in zip(stars, pts):
            col = colour(st.status, self.accent)
            final = st.status not in ("wait", "run")
            rad = (12 if final or st.status == "run" else 6.5) * s
            if st.status == "run":
                ph = (now * 1.6) % 1.0
                for k in (0.0, 0.5):
                    p = (ph + k) % 1.0
                    cr.set_source_rgba(*self.accent, 0.55 * (1 - p))
                    cr.set_line_width(2 * s)
                    cr.new_path()
                    cr.arc(x, y, rad * (1.4 + 2.6 * p), 0, TAU)
                    cr.stroke()
            if final and st.finished_at and now - st.finished_at < 1.2:  # it just lit up: a burst
                p = ease_out((now - st.finished_at) / 1.2)
                cr.set_source_rgba(*col, 0.7 * (1 - p))
                cr.set_line_width(3 * s * (1 - p) + 0.5)
                cr.new_path()
                cr.arc(x, y, rad * (1 + 4 * p), 0, TAU)
                cr.stroke()
                rad *= 1 + 0.5 * (1 - p)
            glow_dot(cr, x, y, rad, col, glow=0.55 if final or st.status == "run" else 0.0)
            # label, outside the ellipse: beside a star, or over/under it at the top and bottom
            summary = self.summary_of(st)
            tcol = FG if st.status != "wait" else MUTED
            scol = VERDICT.get(st.status) if st.status in ("yellow", "red") else MUTED
            if abs(math.cos(ang)) < 0.3:
                above = math.sin(ang) < 0
                ty = y - (52 if summary else 40) * s if above else y + 18 * s
                text(cr, st.title, x, ty, 15 * s, tcol, weight="Bold", align="center")
                if summary:
                    sw = min(gap, 260 * s)
                    text(cr, summary, x - sw / 2, ty + 20 * s, 12.5 * s, scol, width=sw)
            else:
                right = x >= cx
                tx = x + (24 if right else -24) * s
                al = "left" if right else "right"
                text(cr, st.title, tx, y - 19 * s, 15 * s, tcol, weight="Bold", align=al)
                if summary:
                    room = (W - tx if right else tx) - 24 * s
                    text(cr, summary, tx, y + 1 * s, 12.5 * s, scol, align=al, width=max(80 * s, min(280 * s, room)))
            if st.results:
                self.hits.append((x - 22 * s, y - 22 * s, 44 * s, 44 * s, lambda st=st: self.show_detail(st), f"star:{st.id}"))
        return cx, cy

    def summary_of(self, st):
        if st.status == "run":
            return "measuring…" if st.id in dm.STRESS_STEPS else "checking…"
        if not st.results:
            return "nothing found" if st.status == "na" else ""
        rank = {"red": 0, "yellow": 1, "green": 2, "info": 3, "n/a": 4}
        top = min(st.results, key=lambda r: rank.get(r.get("status"), 5))
        more = f"  +{len(st.results) - 1}" if len(st.results) > 1 else ""
        return f"{top.get('summary', '')}{more}"

    def show_detail(self, st):
        self.detail = st.id

    def button(self, cr, x, y, w, h, label, s, action, key, primary=False, sub=None, enabled=True):
        hov = self.hover == key and enabled
        rrect(cr, x, y, w, h, h / 2)
        if primary:
            cr.set_source_rgba(*self.accent, 0.95 if hov else 0.8)
            cr.fill_preserve()
        else:
            cr.set_source_rgba(0.12, 0.10, 0.19, 0.92 if hov else 0.78)
            cr.fill_preserve()
        cr.set_source_rgba(*self.accent, 0.95 if hov else 0.5)
        cr.set_line_width(1.4 * s)
        cr.stroke()
        fg = (1, 1, 1) if primary else FG
        if sub:
            text(cr, label, x + w / 2, y + h / 2 - 19 * s, 17 * s, fg, 1.0 if enabled else 0.4, weight="Bold", align="center")
            text(cr, sub, x + w / 2, y + h / 2 + 2 * s, 12.5 * s, fg, 0.85 if enabled else 0.35, align="center")
        else:
            text(cr, label, x + w / 2, y + h / 2 - 10 * s, 15 * s, fg, 1.0 if enabled else 0.4, align="center")
        if enabled:
            self.hits.append((x, y, w, h, action, key))

    def draw_home(self, cr, W, H, s, cx, cy):
        bw = 290 * s
        y = cy - 118 * s
        for i, (label, sub, args) in enumerate(ACTIONS):
            h = 70 * s if i == 0 else 48 * s
            if i == 0:
                self.button(cr, cx - bw / 2, y, bw, h, label, s, lambda a=args: self.start(a), "act0", primary=True, sub=sub,
                            enabled=not self.waiting)
            else:
                self.button(cr, cx - bw / 2, y, bw, h, f"{label}  ·  {sub.split(' · ')[0]}", s,
                            lambda a=args: self.start(a), f"act{i}", enabled=not self.waiting)
            y += h + 10 * s
        if self.last:
            when = self.last["created"][:16].replace("T", " ")
            word = WORDS.get(self.last["overall"], self.last["overall"] or "")
            msg = f"Last check here: {when} · {word}"
            col = VERDICT.get(self.last["overall"], MUTED)
            tw, th = text(cr, msg, cx, y + 6 * s, 13.5 * s, col, align="center")
            self.hits.append((cx - tw / 2, y + 6 * s, tw, th, lambda: self.open_file(self.last["folder"] / "owner-summary.html"), "last"))
        bw2, bh = 170 * s, 40 * s
        by = H - 70 * s
        self.button(cr, W / 2 - bw2 - 10 * s, by, bw2, bh, "Reports", s, lambda: self.open_file(REPORTS), "reports")
        self.button(cr, W / 2 + 10 * s, by, bw2, bh, "Close", s, self.destroy, "close")

    def ring(self, cr, cx, cy, r, s, frac, col, width=6):
        cr.new_path()  # text leaves a current point behind: an arc would draw a line from it
        cr.set_line_width(width * s)
        cr.set_source_rgba(1, 1, 1, 0.10)
        cr.arc(cx, cy, r, 0, TAU)
        cr.stroke()
        if frac > 0:
            a0 = -math.pi / 2
            for w, al in ((width * 3.2, 0.12), (width * 2, 0.18), (width, 1.0)):  # soft glow under the arc
                cr.new_path()
                cr.set_line_width(w * s)
                cr.set_source_rgba(*col, al)
                cr.arc(cx, cy, r, a0, a0 + TAU * min(frac, 1.0))
                cr.stroke()

    def draw_running(self, cr, W, H, s, cx, cy, now):
        r = 108 * s
        self.ring(cr, cx, cy, r, s, self.shown, self.accent)
        stars = self.run.stars
        done = sum(1 for st in stars if st.status not in ("wait", "run"))
        text(cr, f"{done}/{len(stars)}", cx, cy - 44 * s, 42 * s, FG, weight="Bold", align="center")
        cur = self.run.star(self.run.current)
        text(cr, (cur.title if cur else "starting…"), cx, cy + 10 * s, 15 * s, self.accent, align="center")
        live = self.run.live
        if self.run.current == "cpu_load" and live:
            t = f"{live.get('temp', '?')} °C" + (f" · {live['mhz'] / 1000:.1f} GHz" if live.get("mhz") else "")
            text(cr, t, cx, cy + 32 * s, 14 * s, FG, font=MONO, align="center")
            left = (live.get("total") or 0) - (live.get("t") or 0)
            text(cr, f"{duration(max(0, left))} left", cx, cy + 52 * s, 12 * s, MUTED, align="center")
            self.sparkline(cr, cx, cy + r + 22 * s, 220 * s, 40 * s, s)
        bw, bh = 170 * s, 40 * s
        self.button(cr, W / 2 - bw / 2, H - 70 * s, bw, bh, "Stop", s, self.stop, "stop")

    def sparkline(self, cr, cx, top, w, h, s):
        """CPU temperature during the stress test, against the CPU's own limit."""
        temps = self.run.temps[-180:]
        tj = self.run.live.get("tjmax") or 100
        if len(temps) < 2:
            return
        lo, hi = min(min(temps), 30), max(tj, max(temps))
        x0 = cx - w / 2
        cr.new_path()
        cr.set_source_rgba(1, 1, 1, 0.08)
        rrect(cr, x0 - 8 * s, top - 6 * s, w + 16 * s, h + 12 * s, 8 * s)
        cr.fill()
        ly = top + h - (tj - lo) / (hi - lo) * h  # the limit
        cr.set_source_rgba(*VERDICT["red"], 0.45)
        cr.set_line_width(1 * s)
        cr.set_dash([4 * s, 4 * s])
        cr.move_to(x0, ly)
        cr.line_to(x0 + w, ly)
        cr.stroke()
        cr.set_dash([])
        cr.set_source_rgba(*self.accent, 0.95)
        cr.set_line_width(2 * s)
        for i, t in enumerate(temps):
            x = x0 + i / (len(temps) - 1) * w
            y = top + h - (t - lo) / (hi - lo) * h
            (cr.line_to if i else cr.move_to)(x, y)
        cr.stroke()

    def draw_done(self, cr, W, H, s, cx, cy):
        r = 108 * s
        run = self.run
        if run.phase == "done":
            col = VERDICT.get(run.overall, self.accent)
            word = WORDS.get(run.overall, run.overall or "")
        else:
            col, word = (MUTED, "Stopped" if run.phase == "stopped" else "Didn't finish")
        self.ring(cr, cx, cy, r, s, 1.0 if run.phase == "done" else self.shown, col)
        text(cr, word, cx, cy - 20 * s, 22 * s, col if run.phase == "done" else FG, weight="Bold", align="center")
        n = sum(1 for st in run.stars if st.status not in ("wait", "run"))
        text(cr, f"{n} of {len(run.stars)} checks", cx, cy + 14 * s, 13.5 * s, MUTED, align="center")
        if run.compare:
            y = cy + r + 16 * s
            text(cr, f"Since {run.compare_with}" if run.compare_with else "Since last time", cx, y, 12.5 * s, MUTED, align="center")
            for c in run.compare[:3]:
                y += 20 * s
                text(cr, f"{c.get('name')}  {c.get('before')} → {c.get('after')}", cx, y, 13 * s, FG, font=MONO, align="center")
        bw, bh, gap = 180 * s, 40 * s, 14 * s
        x = W / 2 - (3 * bw + 2 * gap) / 2
        folder = Path(run.folder) if run.folder else None
        self.button(cr, x, H - 70 * s, bw, bh, "Owner summary", s, lambda: self.open_file(folder / "owner-summary.html" if folder else None),
                    "owner", primary=run.phase == "done", enabled=run.phase == "done")
        self.button(cr, x + bw + gap, H - 70 * s, bw, bh, "Full report", s, lambda: self.open_file(folder / "report.html" if folder else None),
                    "report", enabled=run.phase == "done")
        self.button(cr, x + 2 * (bw + gap), H - 70 * s, bw, bh, "New check", s, self.new_check, "new")

    def draw_detail(self, cr, W, H, s, cx, cy):
        st = self.run.star(self.detail)
        if not st:
            self.detail = None
            return
        w = 520 * s
        lines = []
        for r in st.results:
            lines.append((r.get("status"), r.get("title", ""), r.get("summary", "")))
        h = (70 + 62 * len(lines)) * s
        x, y = cx - w / 2, cy - h / 2
        cr.set_source_rgba(0.05, 0.04, 0.09, 0.94)
        rrect(cr, x, y, w, h, 16 * s)
        cr.fill_preserve()
        cr.set_source_rgba(*colour(st.status, self.accent), 0.8)
        cr.set_line_width(1.5 * s)
        cr.stroke()
        text(cr, st.title, x + 24 * s, y + 18 * s, 19 * s, FG, weight="Bold")
        yy = y + 58 * s
        for status, title, summary in lines:
            glow_dot(cr, x + 30 * s, yy + 9 * s, 5 * s, colour(status.replace("n/a", "na"), self.accent), glow=0.4, core=False)
            text(cr, title, x + 46 * s, yy, 14 * s, FG, weight="Bold", width=w - 70 * s)
            text(cr, summary, x + 46 * s, yy + 20 * s, 13 * s, MUTED, width=w - 70 * s, wrap=True)
            yy += 62 * s


def run(demo=False):
    win = Doctor(demo)
    win.show_all()
    Gtk.main()
    return 0
