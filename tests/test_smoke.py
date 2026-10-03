"""Smoke test: run every check against the machine it's on and fail if any check crashes
(a crash turns into an "n/a: This check failed to run" result). Takes about a minute, so it's
opt-in: CHIRON_SMOKE=1 python3 -m unittest tests.test_smoke   (as root on the stick for full coverage)"""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chiron.checks import run_all  # noqa: E402
from chiron.model import Context  # noqa: E402
from chiron.util import own_disks  # noqa: E402


@unittest.skipUnless(os.environ.get("CHIRON_SMOKE"), "set CHIRON_SMOKE=1 to run")
class Smoke(unittest.TestCase):
    def test_no_check_crashes(self):
        with tempfile.TemporaryDirectory() as d:
            ctx = Context(raw_dir=Path(d), quick=True, own=own_disks())
            results = run_all(ctx, progress=lambda *_: None)
            crashed = [r for r in results if r.summary.startswith("This check failed to run")]
            errors = {f.name: f.read_text()[-400:] for f in Path(d).glob("error-*.txt")}
            self.assertFalse(crashed, f"crashed checks: {[r.area for r in crashed]}\n{errors}")
            self.assertTrue(results)

    @unittest.skipUnless(shutil.which("stress-ng"), "stress-ng isn't installed")
    def test_stress_runs(self):
        from chiron.stress import stress
        with tempfile.TemporaryDirectory() as d:
            ctx = Context(raw_dir=Path(d), own=own_disks())
            results = stress(ctx, minutes=0.1, gpu=False, ram=False, progress=lambda *_: None)
            self.assertEqual(results[0].area, "cpu_load")
            self.assertGreater(results[0].evidence.get("duration_s", 0), 3)


if __name__ == "__main__":
    unittest.main()
