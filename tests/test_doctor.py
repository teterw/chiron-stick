"""Tests for the doctor launcher's state (chiron/doctor_model.py): events in, stars out."""
import json
import tempfile
import unittest
from pathlib import Path

from chiron import doctor_model as dm


def res(area, status, summary="…"):
    return {"area": area, "title": area.title(), "status": status, "summary": summary}


START = {"e": "start", "mode": "full", "machine": {"sys_vendor": "Acer", "product_name": "Aspire"},
         "steps": [{"id": "system", "title": "System"}, {"id": "storage", "title": "Storage"},
                   {"id": "cpu_load", "title": "CPU under load"}], "minutes": 2}


class Run(unittest.TestCase):
    def feed(self, *events):
        run = dm.Run()
        for i, e in enumerate(events):
            run.apply(e, now=float(i))
        return run

    def test_stars_light_up(self):
        run = self.feed(START, {"e": "check", "id": "system"})
        self.assertEqual([s.status for s in run.stars], ["run", "wait", "wait"])
        self.assertEqual(run.phase, "running")
        run.apply({"e": "result", "id": "system", "result": res("system", "info")}, now=5)
        run.apply({"e": "check", "id": "storage"}, now=6)
        run.apply({"e": "result", "id": "storage", "result": res("storage:sda", "green")}, now=7)
        run.apply({"e": "result", "id": "storage", "result": res("storage:sdb", "red")}, now=8)
        self.assertEqual(run.star("system").status, "info")
        self.assertEqual(run.star("storage").status, "run", "still running until the next step starts")
        self.assertEqual(run.star("storage").verdict, "red", "the worst of its findings")
        run.apply({"e": "check", "id": "cpu_load"}, now=9)
        self.assertEqual(run.star("storage").status, "red")
        self.assertEqual(run.star("storage").finished_at, 9)

    def test_progress_counts_stress_time(self):
        run = self.feed(START, {"e": "check", "id": "system"}, {"e": "check", "id": "storage"},
                        {"e": "check", "id": "cpu_load"},
                        {"e": "tick", "id": "cpu_load", "t": 60, "total": 120, "temp": 80, "tjmax": 100, "mhz": 3400})
        self.assertAlmostEqual(run.progress(), (2 + 0.5) / 3)
        self.assertEqual(run.live["temp"], 80)
        self.assertEqual(run.temps, [80])

    def test_done(self):
        run = self.feed(START, {"e": "check", "id": "system"},
                        {"e": "done", "overall": "yellow", "folder": "/r/x", "compare": [{"name": "CPU", "before": 96, "after": 78}]})
        self.assertEqual(run.phase, "done")
        self.assertEqual(run.overall, "yellow")
        self.assertEqual(run.star("system").status, "na", "a step that found nothing")
        self.assertAlmostEqual(run.progress(), 1.0)

    def test_stopped_and_unknown_events(self):
        run = self.feed(START, {"e": "nonsense"}, {"e": "check", "id": "nope"}, {"e": "stopped"})
        self.assertEqual(run.phase, "stopped")

    def test_stress_steps_are_slow(self):
        run = self.feed(START, {"e": "check", "id": "cpu_load"})
        self.assertTrue(run.under_load())


class Demo(unittest.TestCase):
    def test_demo_is_a_valid_full_run(self):
        run = dm.Run()
        t = 0.0
        for delay, e in dm.demo_events():
            t += delay
            run.apply(e, now=t)
        self.assertEqual(run.phase, "done")
        self.assertTrue(all(s.status not in ("wait", "run") for s in run.stars))
        self.assertIn("red", [s.status for s in run.stars])


class LastCheck(unittest.TestCase):
    def test_newest_report_of_this_machine(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, vendor, overall in (("2026-10-01_0900_Acer-Aspire", "Acer", "green"),
                                          ("2026-10-04_2142_Acer-Aspire", "Acer", "red"),
                                          ("2026-10-05_1000_Dell-XPS", "Dell", "green")):
                (root / name).mkdir()
                (root / name / "report.json").write_text(json.dumps(
                    {"created": name[:10] + "T21:42:00+07:00", "overall": overall,
                     "machine": {"sys_vendor": vendor, "product_name": "Aspire" if vendor == "Acer" else "XPS"}}))
            last = dm.last_check(root, {"sys_vendor": "Acer", "product_name": "Aspire"})
            self.assertEqual((last["overall"], last["folder"].name), ("red", "2026-10-04_2142_Acer-Aspire"))
            self.assertIsNone(dm.last_check(root, {"sys_vendor": "HP", "product_name": "x"}))


if __name__ == "__main__":
    unittest.main()
