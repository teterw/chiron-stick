"""The Chiron Doctor window: GTK around doctor_scene.Scene (the picture) and doctor_model.Pacer
(events played back at a watchable pace). chiron/doctor.py explains the design."""
import datetime
import json
import os
import pwd
import subprocess
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from chiron import doctor_model as dm  # noqa: E402
from chiron.doctor import CHIRON, LOG, REPORTS, alert, finished_message, personal, this_machine  # noqa: E402
from chiron.doctor_scene import MENU, Scene  # noqa: E402


class Doctor(Gtk.Window):
    def __init__(self, demo):
        super().__init__(title="Chiron Doctor")
        self.demo = demo
        self.set_default_size(1280, 800)
        self.set_icon_name("chiron")
        self.maximize()
        wall, accent = personal()
        machine, spec = this_machine()
        self.machine = machine
        self.scene = Scene(pwd.getpwuid(os.getuid()).pw_name, machine, spec, accent, wall,
                           dm.last_check(REPORTS, machine))
        self.pacer = dm.Pacer()
        self.truth = dm.Run()     # what chiron has really done, whatever the screen shows yet
        self.proc = None
        self.waiting = None       # since when we wait for the password dialog
        self.demo_iter = None
        self.last_draw = 0.0
        self.alerted = False
        area = Gtk.DrawingArea()
        area.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.POINTER_MOTION_MASK)
        area.connect("draw", self.on_draw)
        area.connect("button-press-event", self.on_click)
        area.connect("motion-notify-event", self.on_motion)
        self.add(area)
        self.area = area
        self.connect("key-press-event", self.on_key)
        self.connect("destroy", self.on_destroy)
        self.connect("focus-in-event", lambda *a: self.set_urgency_hint(False))
        self.add_tick_callback(self.tick)

    @property
    def run(self):
        return self.pacer.run

    # ------------------------------------------------ running chiron

    def start(self, args):
        if self.proc or self.demo_iter or self.run.phase == "running":
            return
        self.scene.detail = None
        self.pacer = dm.Pacer()
        self.truth = dm.Run()
        self.alerted = False
        if self.demo:
            self.play(dm.demo_events())
            return
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a") as log:
            log.write(f"\n=== {datetime.datetime.now():%Y-%m-%d %H:%M:%S} chiron {' '.join(args)}\n")
            log.flush()
            try:
                self.proc = subprocess.Popen(["pkexec", CHIRON, "--events", *args], stdin=subprocess.PIPE,
                                             stdout=subprocess.PIPE, stderr=log, text=True, bufsize=1)
            except OSError as err:
                self.note(f"can't start chiron: {err}", "red")
                return
        self.waiting = time.monotonic()
        GLib.io_add_watch(self.proc.stdout.fileno(), GLib.PRIORITY_DEFAULT,
                          GLib.IOCondition.IN | GLib.IOCondition.HUP, self.on_output)

    def receive(self, e):
        now = time.monotonic()
        if e.get("e") == "start":
            self.waiting = None
        self.truth.apply(e, now)
        self.pacer.push(e, at=now)

    def on_output(self, _fd, _cond):
        line = self.proc.stdout.readline() if self.proc else ""
        if line:
            try:
                self.receive(json.loads(line))
            except ValueError:
                pass
            return True
        rc = self.proc.wait() if self.proc else 0
        self.proc, self.waiting = None, None
        if self.truth.phase == "idle":
            self.note("cancelled" if rc in (126, 127) else f"chiron couldn't start (exit {rc}): see {LOG}", "na")
        elif self.truth.phase == "running":
            self.pacer.push({"e": "stopped"})
            self.note(f"chiron ended unexpectedly (exit {rc}): see {LOG}", "red")
        return False

    def note(self, msg, status):
        """A line in the log panel, outside a run (cancelled, errors)."""
        self.run.say(time.monotonic(), f"{'Note':<15}{msg[:1].upper()}{msg[1:]}", status)

    def stop(self):
        if self.demo_iter is not None:
            self.demo_iter = None
            self.receive({"e": "stopped"})
        elif self.proc:
            try:
                self.proc.stdin.write("stop\n")
                self.proc.stdin.flush()
            except OSError:
                pass
            self.note("stopping safely…", "run")

    def play(self, events):
        """--demo: a scripted run, no root."""
        self.demo_iter = iter(events)

        def step():
            if self.demo_iter is None:
                return
            try:
                delay, e = next(self.demo_iter)
            except StopIteration:
                self.demo_iter = None
                return

            def fire():
                if self.demo_iter is not None:
                    self.receive(e)
                    step()
                return False
            GLib.timeout_add(int(delay * 1000), fire)
        step()

    def open_file(self, path):
        if path and Path(path).exists():
            subprocess.Popen(["xdg-open", str(path)], start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            self.note("the demo doesn't write a report" if self.demo else "nothing there yet", "na")

    def new_check(self):
        if self.run.phase == "running":
            return
        self.pacer = dm.Pacer()
        self.truth = dm.Run()
        self.scene.detail = None
        self.scene.show_specs = False
        self.scene.last = dm.last_check(REPORTS, self.machine)

    # ------------------------------------------------ actions

    def act(self, action):
        kind, _, arg = action.partition(":")
        folder = Path(self.run.folder) if self.run.folder else None
        if kind == "menu":
            self.scene.menu_sel = int(arg)
            self.start(MENU[int(arg)][2])
        elif kind == "node":
            self.scene.detail = arg
        elif kind == "detail":
            self.scene.detail = None
        elif action == "cmd:specs":
            self.scene.show_specs = not self.scene.show_specs
        elif action == "specs:close":
            self.scene.show_specs = False
        elif action == "last" and self.scene.last:
            self.open_file(self.scene.last["folder"] / "owner-summary.html")
        elif action == "cmd:start":
            self.start(MENU[self.scene.menu_sel][2])
        elif action == "cmd:reports":
            self.open_file(REPORTS)
        elif action == "cmd:close":
            self.destroy()
        elif action == "cmd:stop":
            self.stop()
        elif action == "cmd:owner" and self.run.phase == "done":
            self.open_file(folder / "owner-summary.html" if folder else None)
        elif action == "cmd:report" and self.run.phase == "done":
            self.open_file(folder / "report.html" if folder else None)
        elif action == "cmd:new":
            self.new_check()

    def on_click(self, _w, ev):
        for x, y, w, h, action in reversed(self.scene.hits):
            if x <= ev.x <= x + w and y <= ev.y <= y + h:
                self.act(action)
                break
        return True

    def on_motion(self, _w, ev):
        hover = next((a for x, y, w, h, a in reversed(self.scene.hits) if x <= ev.x <= x + w and y <= ev.y <= y + h), None)
        if hover != self.scene.hover:
            self.scene.hover = hover
            if hover and hover.startswith("menu:"):
                self.scene.menu_sel = int(hover[5:])
            win = self.area.get_window()
            if win:
                win.set_cursor(Gdk.Cursor.new_from_name(self.get_display(), "pointer") if hover and hover != "detail:close" else None)
        return True

    def on_key(self, _w, ev):
        name = Gdk.keyval_name(ev.keyval) or ""
        phase = self.run.phase
        if ev.state & Gdk.ModifierType.CONTROL_MASK and name in ("q", "w"):
            self.destroy()
        elif name in ("i", "I") and self.run.specs and phase != "idle":
            self.act("cmd:specs")
        elif name == "Escape":
            if self.scene.show_specs:
                self.scene.show_specs = False
            elif self.scene.detail:
                self.scene.detail = None
            elif phase in ("done", "stopped", "failed"):
                self.new_check()
            elif phase == "idle" and not self.proc:
                self.destroy()
        elif phase == "idle" and not self.proc:
            if name in ("1", "2", "3", "4", "5", "KP_1", "KP_2", "KP_3", "KP_4", "KP_5"):
                self.act(f"menu:{int(name[-1]) - 1}")
            elif name in ("Up", "k"):
                self.scene.menu_sel = (self.scene.menu_sel - 1) % len(MENU)
            elif name in ("Down", "j", "Tab"):
                self.scene.menu_sel = (self.scene.menu_sel + 1) % len(MENU)
            elif name in ("Return", "KP_Enter"):
                self.act("cmd:start")
            elif name in ("r", "R"):
                self.act("cmd:reports")
        elif phase == "running" and name in ("s", "S"):
            self.act("cmd:stop")
        elif phase in ("done", "stopped", "failed"):
            self.act({"o": "cmd:owner", "f": "cmd:report", "n": "cmd:new"}.get(name.lower(), "none"))
        return True

    def on_destroy(self, *_a):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.stdin.close()  # end of input: chiron stops the run safely (events.watch_stop)
            except OSError:
                pass
        Gtk.main_quit()

    # ------------------------------------------------ drawing

    def tick(self, _w, _clock):
        now = time.monotonic()
        self.pacer.update(now)
        if not self.alerted and self.run.phase in ("done", "stopped", "failed"):
            self.alerted = True
            took = (self.truth.ended_at or now) - (self.truth.started_at or now)
            msg = finished_message(self.run, took)
            if msg:  # a long run: say it's finished, in case nobody is watching
                alert(*msg)
                if not self.is_active():
                    self.set_urgency_hint(True)
        # under a stress test: fewer frames, so the window doesn't take CPU time from the test
        if now - self.last_draw >= (0.125 if self.truth.under_load() else 0.0):
            self.area.queue_draw()
        return True

    def on_draw(self, widget, cr):
        now = time.monotonic()
        self.last_draw = now
        self.scene.render(cr, widget.get_allocated_width(), widget.get_allocated_height(), now, self.run,
                          waiting=self.waiting, under_load=self.truth.under_load())
        return True


def run(demo=False):
    win = Doctor(demo)
    win.show_all()
    Gtk.main()
    return 0
