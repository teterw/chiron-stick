"""The doctor launcher's state, without any drawing: the events of one `chiron --events` run
(chiron/events.py) become stars that light up, a progress fraction, live CPU readings and a verdict.
Kept apart from the window so it can be tested without a display."""
import json
from pathlib import Path

from chiron.model import Status, worst

STRESS_STEPS = {"cpu_load", "ram", "gpu"}  # slow steps: the window redraws less while they run


class Star:
    def __init__(self, sid, title):
        self.id, self.title = sid, title
        self.status = "wait"      # wait | run | green | yellow | red | info | na
        self.results = []         # result dicts (area, title, status, summary, …)
        self.started_at = self.finished_at = None

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
        self.started_at = self.ended_at = None

    def star(self, sid):
        return next((s for s in self.stars if s.id == sid), None)

    def _finish_current(self, now):
        s = self.star(self.current)
        if s and s.status == "run":
            s.status, s.finished_at = s.verdict, now
        self.current = None

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
        elif kind == "result":
            s = self.star(e.get("id"))
            if s and isinstance(e.get("result"), dict):
                s.results.append(e["result"])
        elif kind == "tick":
            self.live = {k: e.get(k) for k in ("t", "total", "temp", "tjmax", "mhz")}
            if e.get("temp") is not None:
                self.temps.append(e["temp"])
        elif kind == "log":
            self.log = (self.log + [e.get("text", "")])[-50:]
        elif kind == "done":
            self._finish_current(now)
            self.phase, self.ended_at = "done", now
            self.overall, self.folder = e.get("overall"), e.get("folder")
            self.compare, self.compare_with = e.get("compare") or [], e.get("compare_with")
        elif kind == "stopped":
            self._finish_current(now)
            self.phase, self.ended_at = "stopped", now

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
    yield 0.4, {"e": "start", "mode": "full", "machine": {"sys_vendor": "Acer", "product_name": "Aspire A515-58M"},
                "steps": [{"id": i, "title": t} for i, t in steps], "minutes": 0.5}
    for sid, title in steps:
        yield 0.3, {"e": "check", "id": sid}
        if sid == "cpu_load":
            for t in range(1, 31):
                temp = round(48 + 38 * (1 - 0.93 ** t))
                yield 0.25, {"e": "tick", "id": "cpu_load", "t": t, "total": 30, "temp": temp, "tjmax": 100, "mhz": 3400 - 4 * t}
            yield 0.1, {"e": "result", "id": sid, "result": {"area": "cpu_load", "title": title, "status": "green",
                                                            "summary": "30 s of full load; max 85 °C (limit 100 °C); clock 3396 → 3280 MHz"}}
            continue
        for status, summary in found.get(sid, []):
            yield 0.9, {"e": "result", "id": sid, "result": {"area": sid, "title": title, "status": status, "summary": summary}}
    yield 0.6, {"e": "done", "overall": "red", "folder": "", "compare_with": "2026-09-12 10:05",
                "compare": [{"name": "CPU max temperature", "before": "96 °C", "after": "85 °C"},
                            {"name": "Battery health", "before": "74%", "after": "71%"}]}
