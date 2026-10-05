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


class Pacing(unittest.TestCase):
    """A check that finishes in a second still plays out star by star (Tete: "even if the test
    finishes within a second I want the star animation to go slowly to each one")."""

    def burst(self):
        pacer = dm.Pacer()
        for e in (START, {"e": "check", "id": "system"}, {"e": "result", "id": "system", "result": res("system", "info")},
                  {"e": "check", "id": "storage"}, {"e": "result", "id": "storage", "result": res("storage", "red")},
                  {"e": "done", "overall": "red", "folder": "/r/x"}):
            pacer.push(e)
        return pacer

    def times(self, pacer, until=30.0, step=0.05):
        """When each event reached the screen."""
        seen, t = [], 0.0
        while t <= until:
            for e in pacer.update(t):
                seen.append((e["e"], e.get("id"), round(t, 2)))
            t += step
        return seen

    def test_everything_at_once_plays_slowly(self):
        P = dm.Pacer
        seen = self.times(self.burst())
        at = {(k, i): t for k, i, t in seen}
        self.assertEqual(at[("start", None)], 0.0)
        first = at[("check", "system")]
        self.assertAlmostEqual(first, P.INTRO, delta=0.06)
        self.assertGreaterEqual(at[("result", "system")] - first, P.BEAM + P.SCAN - 0.01, "beam, then a scan")
        self.assertGreaterEqual(at[("check", "storage")] - at[("result", "system")], P.REVEAL - 0.01, "time to see it")
        self.assertGreaterEqual(at[("done", None)] - at[("result", "storage")], P.END - 0.01)
        self.assertEqual([k for k, _, _ in seen], ["start", "check", "result", "check", "result", "done"])

    def test_slow_real_events_are_not_delayed_more(self):
        pacer = dm.Pacer()
        pacer.push(START)
        pacer.update(0.0)
        pacer.push({"e": "check", "id": "cpu_load"})
        pacer.update(5.0)
        self.assertEqual(pacer.run.current, "cpu_load")
        pacer.push({"e": "result", "id": "cpu_load", "result": res("cpu_load", "green")})
        self.assertEqual(len(pacer.update(600.0)), 1, "a 10-minute test shows its result when it comes")

    def test_ticks_wait_behind_their_step(self):
        pacer = dm.Pacer()
        for e in (START, {"e": "check", "id": "cpu_load"}, {"e": "tick", "id": "cpu_load", "t": 1, "total": 60, "temp": 70}):
            pacer.push(e)
        pacer.update(0.0)
        pacer.update(0.4)
        self.assertEqual(pacer.run.temps, [], "the tick belongs to a step not on screen yet")
        pacer.update(dm.Pacer.INTRO + 0.01)
        self.assertEqual(pacer.run.temps, [70])

    def test_stop_shows_at_once(self):
        pacer = self.burst()
        pacer.queue.pop()  # no done: stopped instead
        pacer.push({"e": "stopped"})
        pacer.update(0.0)
        self.assertEqual(pacer.run.phase, "stopped")
        self.assertFalse(pacer.queue)

    def test_reveal_time_and_log(self):
        pacer = self.burst()
        self.times(pacer)
        st = pacer.run.star("storage")
        self.assertIsNotNone(st.revealed_at, "the moment its first finding showed")
        kinds = [entry[2] for entry in pacer.run.feed]
        self.assertIn("red", kinds)
        self.assertEqual(pacer.run.feed[-1][2], "red", "the log ends with the verdict")


class DoneAlert(unittest.TestCase):
    def test_only_long_runs_ring(self):
        from chiron import doctor
        run = dm.Run()
        for i, e in enumerate((START, {"e": "check", "id": "system"}, {"e": "done", "overall": "red", "folder": "/r"})):
            run.apply(e, now=float(i))
        self.assertIsNone(doctor.finished_message(run, 20), "a quick check: no alert")
        title, body = doctor.finished_message(run, 621)
        self.assertEqual(title, "Check finished")
        self.assertEqual(body, "Problem found · 3 checks · 10:21")
        run.phase = "stopped"
        self.assertEqual(doctor.finished_message(run, 300)[1], "Stopped · 3 checks · 5:00")


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
