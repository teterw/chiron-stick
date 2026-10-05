"""Tests for chiron's machine-readable progress (chiron --events), which the doctor launcher reads."""
import io
import json
import os
import threading
import unittest
from types import SimpleNamespace
from unittest import mock

from chiron import checks, events
from chiron.model import Context, Result, Status


class Emitting(unittest.TestCase):
    def test_json_lines(self):
        out = io.StringIO()
        ev = events.Events(out)
        ev.emit("result", id="battery", result={"status": "green"})
        ev.say("  checking battery…")
        lines = [json.loads(l) for l in out.getvalue().splitlines()]
        self.assertEqual(lines[0], {"e": "result", "id": "battery", "result": {"status": "green"}})
        self.assertEqual(lines[1], {"e": "log", "text": "checking battery…"})

    def test_text_mode_prints(self):
        ev = events.Events()
        self.assertFalse(ev.enabled)
        with mock.patch("builtins.print") as p:
            ev.say("hello")
            ev.emit("result", id="x")  # nothing: text mode prints the summary at the end instead
        p.assert_called_once_with("hello")


class Hooks(unittest.TestCase):
    def test_run_all_reports_each_module(self):
        fake = {name: SimpleNamespace(run=lambda ctx, n=name: [Result(n, n.title(), Status.GREEN, "ok")])
                for name in checks.MODULES}
        seen = []
        with mock.patch("importlib.import_module", side_effect=lambda m: fake[m.rsplit(".", 1)[1]]):
            results = checks.run_all(Context(), only={"battery", "storage"}, progress=lambda s: None,
                                     on_check=lambda m: seen.append(("check", m)),
                                     on_result=lambda m, r: seen.append(("result", m, r.area)))
        self.assertEqual([r.area for r in results], ["battery", "storage"])
        self.assertEqual(seen, [("check", "battery"), ("result", "battery", "battery"),
                                ("check", "storage"), ("result", "storage", "storage")])

    def test_every_module_has_a_title(self):
        for name in checks.MODULES:
            self.assertIn(name, checks.TITLES)


class Stopping(unittest.TestCase):
    def watch(self, data):
        r, w = os.pipe()
        stopped = threading.Event()
        t = events.watch_stop(os.fdopen(r), interrupt=stopped.set)
        with os.fdopen(w, "w") as f:
            f.write(data)
        t.join(2)
        return stopped.is_set()

    def test_stop_line(self):
        self.assertTrue(self.watch("stop\n"))

    def test_launcher_gone(self):
        """stdin closing (the launcher crashed or was closed) stops the run too: no stress test
        is ever left running with nobody watching."""
        self.assertTrue(self.watch(""))

    def test_other_lines_ignored(self):
        r, w = os.pipe()
        stopped = threading.Event()
        events.watch_stop(os.fdopen(r), interrupt=stopped.set)
        f = os.fdopen(w, "w")
        f.write("hello\n")
        f.flush()
        self.assertFalse(stopped.wait(0.3))
        f.close()


class ReportFolder(unittest.TestCase):
    def test_two_checks_in_one_minute_keep_both(self):
        """The doctor makes quick reruns easy: a second report in the same minute must not
        overwrite the first one."""
        import tempfile
        from pathlib import Path
        from chiron.cli import unique_folder
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "2026-10-05_1308_Acer-Aspire"
            self.assertEqual(unique_folder(f), f)
            f.mkdir()
            self.assertEqual(unique_folder(f).name, "2026-10-05_1308_Acer-Aspire-2")
            (Path(tmp) / "2026-10-05_1308_Acer-Aspire-2").mkdir()
            self.assertEqual(unique_folder(f).name, "2026-10-05_1308_Acer-Aspire-3")


if __name__ == "__main__":
    unittest.main()
