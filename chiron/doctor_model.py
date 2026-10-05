"""The doctor launcher's state, without any drawing: the events of one `chiron --events` run
(chiron/events.py) become stars that light up, a progress fraction, live CPU readings and a verdict.
Kept apart from the window so it can be tested without a display."""
import json
from collections import deque
from pathlib import Path

from chiron.advice import todo
from chiron.model import Status, worst

STRESS_STEPS = {"cpu_load", "ram", "gpu"}  # slow steps: the window redraws less while they run


class Star:
    def __init__(self, sid, title):
        self.id, self.title = sid, title
        self.status = "wait"      # wait | run | green | yellow | red | info | na
        self.results = []         # result dicts (area, title, status, summary, …)
        self.started_at = self.finished_at = None
        self.revealed_at = None   # when its first finding showed (the star lights up then)

    @property
    def verdict(self):
        """The worst of its findings so far: green/yellow/red, info (facts only) or na."""
        return worst([Status(r["status"]) for r in self.results]).value.replace("n/a", "na")


class Run:
    def __init__(self):
        self.phase = "idle"       # idle | running | done | stopped | failed
        self.mode = None
        self.machine = {}
        self.stars = []
        self.current = None
        self.live = {}            # last CPU tick: t, total, temp, tjmax, mhz
        self.temps = []           # CPU temperatures during the stress test, one per second
        self.overall = self.folder = None
        self.compare, self.compare_with = [], None
        self.log = []
        self.feed = []            # the log panel: (time, text, status) per line
        self.specs = None         # the spec sheet: [(section, [(label, value), …]), …]
        self.started_at = self.ended_at = None

    def star(self, sid):
        return next((s for s in self.stars if s.id == sid), None)

    def _finish_current(self, now):
        s = self.star(self.current)
        if s and s.status == "run":
            s.status, s.finished_at = s.verdict, now
            if not s.results:
                self.feed.append((now, f"{s.title:<15}Nothing to check here", "na"))
        self.current = None

    def say(self, now, text, status):
        self.feed = (self.feed + [(now, text, status)])[-60:]

    def apply(self, e, now):
        kind = e.get("e")
        if kind == "start":
            self.__init__()
            self.phase, self.mode, self.machine, self.started_at = "running", e.get("mode"), e.get("machine") or {}, now
            self.stars = [Star(s["id"], s["title"]) for s in e.get("steps", [])]
        elif kind == "check":
            self._finish_current(now)
            s = self.star(e.get("id"))
            if s:
                s.status, s.started_at, self.current = "run", now, s.id
                self.say(now, f"{s.title:<15}Checking…", "run")
        elif kind == "result":
            s = self.star(e.get("id"))
            r = e.get("result")
            if s and isinstance(r, dict):
                s.results.append(r)
                s.revealed_at = s.revealed_at or now
                text = r.get("summary", "")
                self.say(now, f"{s.title:<15}{text[:1].upper()}{text[1:]}", r.get("status", "info").replace("n/a", "na"))
        elif kind == "tick":
            self.live = {k: e.get(k) for k in ("t", "total", "temp", "tjmax", "mhz")}
            if e.get("temp") is not None:
                self.temps.append(e["temp"])
            if (e.get("t") or 0) % 30 == 0 and e.get("t"):
                self.say(now, f"{'CPU load':<15}{e.get('temp')} °C · {e.get('mhz') or '?'} MHz · {e['t']} s", "run")
        elif kind == "specs":
            self.specs = e.get("lines") or None
            if self.specs:
                self.say(now, f"{'Spec sheet':<15}Hardware inventory ready: press I to see it", "info")
        elif kind == "log":
            self.log = (self.log + [e.get("text", "")])[-50:]
        elif kind == "done":
            self._finish_current(now)
            self.phase, self.ended_at = "done", now
            self.overall, self.folder = e.get("overall"), e.get("folder")
            self.compare, self.compare_with = e.get("compare") or [], e.get("compare_with")
            for t in todo([r for st in self.stars for r in st.results])[:4]:
                self.say(now, f"{'To do':<15}{t['action']}" + (f" Part: {t['part']}." if t.get("part") else ""), t["status"])
            for c in self.compare[:3]:
                self.say(now, f"{'Since last':<15}{c.get('name')}: {c.get('before')} → {c.get('after')}", "info")
            self.say(now, f"{'Diagnosis':<15}{ {'green': 'All good', 'yellow': 'Worth a look', 'red': 'Problem found'}.get(self.overall, self.overall)}", self.overall or "info")
        elif kind == "stopped":
            self._finish_current(now)
            self.phase, self.ended_at = "stopped", now
            self.say(now, f"{'Stopped':<15}On request: everything cleaned up", "na")

    def progress(self):
        """0..1: finished steps, plus how far the CPU load test has got."""
        if not self.stars:
            return 0.0
        if self.phase == "done":
            return 1.0
        n = sum(1 for s in self.stars if s.status not in ("wait", "run"))
        if self.current == "cpu_load" and self.live.get("total"):
            n += min(1.0, (self.live.get("t") or 0) / self.live["total"])
        return n / len(self.stars)

    def under_load(self):
        return self.phase == "running" and self.current in STRESS_STEPS


class Pacer:
    """Plays a run's events back at a pace people can follow: chiron may finish ten checks in two
    seconds, but on screen a beam travels to each star, the star scans, its result locks in, and
    only then does the next one start. Slow steps (the stress test) take as long as they really do.
    Events arrive with push(); update(now) applies the ones that are due to self.run."""
    INTRO = 0.8    # before the first beam: the chart wakes up
    BEAM = 0.6     # the beam travels along the link to the next star
    SCAN = 1.1     # the star scans at least this long before its first finding shows
    GAP = 0.35     # between two findings of one star
    REVEAL = 0.7   # a finding stays in focus before the beam moves on
    END = 0.9      # after the last finding, before the verdict

    def __init__(self):
        self.run = Run()
        self.queue = deque()
        self.started = self.step_at = self.result_at = None
        self.hurry = False        # stopped: show everything left at once

    def push(self, e):
        if e.get("e") == "stopped":
            self.hurry = True
        self.queue.append(e)

    def due(self, e):
        kind = e.get("e")
        if self.hurry or kind not in ("check", "result", "done"):
            return float("-inf")
        if kind == "check" and self.step_at is None:
            return (self.started if self.started is not None else float("-inf")) + self.INTRO
        scanned = (self.step_at if self.step_at is not None else float("-inf")) + self.BEAM + self.SCAN
        last = self.result_at if self.result_at is not None else float("-inf")
        return max(scanned, last + {"result": self.GAP, "check": self.REVEAL, "done": self.END}[kind])

    def update(self, now):
        shown = []
        while self.queue and self.due(self.queue[0]) <= now:
            e = self.queue.popleft()
            kind = e.get("e")
            if kind == "start":
                self.started, self.step_at, self.result_at = now, None, None
            elif kind == "check":
                self.step_at, self.result_at = now, None
            elif kind == "result":
                self.result_at = now
            self.run.apply(e, now)
            shown.append(e)
        return shown

    def busy(self):
        return bool(self.queue)


def last_check(reports, machine):
    """The newest report of this machine in ~/reports: {created, overall, folder}, or None."""
    best = None
    for f in Path(reports).glob("*/report.json"):
        try:
            r = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        m = r.get("machine") or {}
        if (m.get("sys_vendor"), m.get("product_name")) != (machine.get("sys_vendor"), machine.get("product_name")):
            continue
        if not best or r.get("created", "") > best["created"]:
            best = {"created": r.get("created", ""), "overall": r.get("overall"), "folder": f.parent}
    return best


def demo_events():
    """A scripted full check (about 20 s) for `chiron doctor --demo`: no root, nothing measured."""
    steps = [("system", "System"), ("battery", "Battery"), ("storage", "Storage"), ("memory", "Memory"),
             ("cpu", "CPU"), ("sensors", "Sensors"), ("kernel_log", "Kernel log"), ("devices", "Devices"),
             ("diskspace", "Disk space"), ("win11", "Windows 11"), ("cpu_load", "CPU under load"),
             ("ram", "RAM test"), ("gpu", "Graphics test")]
    found = {"system": [("info", "Acer Aspire A515-58M · i5-13420H · 16 GB")],
             "battery": [("yellow", "holds 71% of its design capacity · 412 cycles")],
             "storage": [("red", "SSD: 3 pending sectors: back up now"), ("green", "NVMe: 4% used, no errors")],
             "memory": [("green", "16 GB, no hardware memory errors")], "cpu": [("info", "13th Gen Intel i5-13420H, 12 threads")],
             "sensors": [("green", "CPU 46 °C at rest")], "kernel_log": [("green", "no hardware errors")],
             "devices": [("green", "every device has a working driver")], "diskspace": [("yellow", "Windows: 9% free (21 GB)")],
             "win11": [("green", "ready: TPM 2.0, Secure Boot, supported CPU")],
             "ram": [("green", "memtester pass, no errors")], "gpu": [("green", "Intel UHD: glmark2 score 2140")]}
    evidence = {("battery", 0): {"manufacturer": "SMP", "model": "AP18C8K", "technology": "Li-ion", "unit": "Wh", "design": 48.0},
                ("storage", 0): {"model": "WDC WDS240G2G0A", "size_bytes": 240_057_409_536, "class": "ssd", "transport": "sata"},
                ("storage", 1): {"model": "SAMSUNG MZVLQ512", "size_bytes": 512_110_190_592, "class": "nvme"}}
    yield 0.4, {"e": "start", "mode": "full", "machine": {"sys_vendor": "Acer", "product_name": "Aspire A515-58M"},
                "steps": [{"id": i, "title": t} for i, t in steps], "minutes": 0.5}
    yield 0.2, {"e": "specs", "lines": [
        ["System", [["Computer", "Acer Aspire A515-58M"], ["Board", "RPL Birkin_RTU"], ["BIOS", "Insyde Corp. V1.04 (08/16/2023)"]]],
        ["Processor", [["Processor", "Intel Core i5-13420H"], ["Cores", "8 cores, 12 threads"], ["Top speed", "4.6 GHz"],
                       ["L3 cache", "12 MiB"]]],
        ["Memory", [["Installed", "16 GB · 2 of 2 slots used · up to 32 GB"],
                    ["DIMM A", "8 GB · DDR4 · SODIMM · 3200 MT/s · Samsung M471A1K43DB1-CWE"],
                    ["DIMM B", "8 GB · DDR4 · SODIMM · 3200 MT/s · Samsung M471A1K43DB1-CWE"],
                    ["To add RAM", "DDR4 SODIMM 3200 MT/s · no free slot: replace a stick"]]],
        ["Storage", [["SSD", "WDC WDS240G2G0A · 240 GB · sata"], ["NVMe SSD", "SAMSUNG MZVLQ512 · 512 GB · nvme"]]],
        ["Graphics", [["GPU", "Intel Raptor Lake-P UHD Graphics (driver i915)"]]],
        ["Screen", [["Built-in", "15.5-inch · 1920×1080 · AUO B156HAN02.1"]]],
        ["Battery", [["Battery", "SMP AP18C8K · Li-ion · 34 of 48 Wh design (71%) · 412 cycles"]]],
        ["Other devices", [["Network", "Intel Raptor Lake PCH CNVi WiFi"], ["Audio", "Intel Raptor Lake-P/U/H cAVS"],
                           ["Camera", "ACER FHD User Facing"]]]]}
    for sid, title in steps:
        yield 0.3, {"e": "check", "id": sid}
        if sid == "cpu_load":
            for t in range(1, 31):
                temp = round(48 + 38 * (1 - 0.93 ** t))
                yield 0.25, {"e": "tick", "id": "cpu_load", "t": t, "total": 30, "temp": temp, "tjmax": 100, "mhz": 3400 - 4 * t}
            yield 0.1, {"e": "result", "id": sid, "result": {"area": "cpu_load", "title": title, "status": "green",
                                                            "summary": "30 s of full load; max 85 °C (limit 100 °C); clock 3396 → 3280 MHz"}}
            continue
        for k, (status, summary) in enumerate(found.get(sid, [])):
            ev = evidence.get((sid, k), {})
            yield 0.9, {"e": "result", "id": sid, "result": {"area": sid, "title": title, "status": status, "summary": summary,
                                                            "evidence": ev}}
    yield 0.6, {"e": "done", "overall": "red", "folder": "", "compare_with": "2026-09-12 10:05",
                "compare": [{"name": "CPU max temperature", "before": "96 °C", "after": "85 °C"},
                            {"name": "Battery health", "before": "74%", "after": "71%"}]}
