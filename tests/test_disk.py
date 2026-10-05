"""Tests for the disk deep-dive: the SMART table (checks/storage.smart_table) and the read scan
(chiron/disk_scan.py)."""
import os
import tempfile
import unittest

from chiron import disk_scan
from chiron.checks import storage

ATA = {"ata_smart_attributes": {"table": [
    {"id": 5, "name": "Reallocated_Sector_Ct", "value": 100, "worst": 100, "thresh": 10, "raw": {"value": 0}},
    {"id": 9, "name": "Power_On_Hours", "value": 99, "worst": 99, "thresh": 0, "raw": {"value": 5769}},
    {"id": 187, "name": "Reported_Uncorrect", "value": 100, "worst": 100, "thresh": 0, "raw": {"value": 16}},
    {"id": 197, "name": "Current_Pending_Sector", "value": 100, "worst": 100, "thresh": 0, "raw": {"value": 3}},
    {"id": 194, "name": "Temperature_Celsius", "value": 60, "worst": 46, "thresh": 0, "raw": {"value": 40}},
    {"id": 3, "name": "Spin_Up_Time", "value": 5, "worst": 5, "thresh": 21, "raw": {"value": 0},
     "when_failed": "now"}]}}
NVME = {"nvme_smart_health_information_log": {"critical_warning": 0, "percentage_used": 84, "media_errors": 0,
                                               "available_spare": 100, "available_spare_threshold": 10,
                                               "power_on_hours": 3100, "unsafe_shutdowns": 52, "temperature": 38}}


class SmartTable(unittest.TestCase):
    def test_ata(self):
        rows = {r["name"]: r for r in storage.smart_table(ATA)}
        self.assertEqual(rows["Current pending sectors"]["level"], "bad")
        self.assertEqual(rows["Reported uncorrectable errors"]["level"], "watch")
        self.assertEqual(rows["Reallocated sectors"]["level"], "ok")
        self.assertEqual(rows["Power-on hours"]["value"], "5769")
        self.assertEqual(rows["Spin up time"]["level"], "bad", "an attribute at or below its threshold is failing")
        order = [r["level"] for r in storage.smart_table(ATA)]
        self.assertEqual(order, sorted(order, key=["bad", "watch", "ok"].index), "the worrying rows first")

    def test_nvme(self):
        rows = {r["name"]: r for r in storage.smart_table(NVME)}
        self.assertEqual(rows["Endurance used"]["value"], "84%")
        self.assertEqual(rows["Endurance used"]["level"], "watch")
        self.assertEqual(rows["Media errors"]["level"], "ok")

    def test_nothing(self):
        self.assertEqual(storage.smart_table({}), [])


class Scan(unittest.TestCase):
    def test_reads_samples_across_a_file(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.truncate(64 * 1024 * 1024)
            path = f.name
        try:
            seen = []
            out = disk_scan.scan(path, os.path.getsize(path), samples=16, chunk=1024 * 1024,
                                 emit=lambda kind, **d: seen.append(d))
            self.assertEqual(len(out["samples"]), 16)
            self.assertEqual(len(seen), 16)
            self.assertEqual(seen[-1]["i"], 15)
            self.assertEqual(out["errors"], 0)
            self.assertGreater(out["median_mbps"], 0)
            self.assertLessEqual(max(s["offset"] for s in out["samples"]) + 1024 * 1024, 64 * 1024 * 1024)
        finally:
            os.unlink(path)

    def test_grading(self):
        good = [{"mbps": 500, "error": False}] * 100
        self.assertEqual(disk_scan.grade({"samples": good, "errors": 0, "median_mbps": 500})[0], "green")
        slow = good[:95] + [{"mbps": 60, "error": False}] * 5
        status, summary = disk_scan.grade({"samples": slow, "errors": 0, "median_mbps": 500})
        self.assertEqual(status, "yellow")
        self.assertIn("slow", summary)
        bad = good[:99] + [{"mbps": None, "error": True}]
        self.assertEqual(disk_scan.grade({"samples": bad, "errors": 1, "median_mbps": 500})[0], "red")


class InTheReport(unittest.TestCase):
    def test_smart_table_and_scan_graph(self):
        import tempfile
        from pathlib import Path
        from chiron import report
        st = {"area": "storage", "title": "Disk", "status": "red", "summary": "3 pending",
              "evidence": {"smart_table": storage.smart_table(ATA), "class": "ssd"}}
        sc = {"area": "disk_scan", "title": "Disk scan", "status": "red", "summary": "1 of 4 areas couldn't be read",
              "evidence": {"curve": [500, 510, None, 505], "class": "ssd", "size_bytes": 240_057_409_536}}
        rep = {"chiron": "t", "created": "2026-10-05T15:00:00+07:00", "machine": {}, "results": [st, sc]}
        with tempfile.TemporaryDirectory() as tmp:
            report.write_all(rep, Path(tmp))
            page = (Path(tmp) / "report.html").read_text()
        self.assertIn("Current pending sectors", page)
        self.assertIn("<svg", page)
        self.assertNotIn("smart_table", page, "shown as a table, not as raw data")
        self.assertEqual(rep["todo"][1]["area"], "disk_scan")


if __name__ == "__main__":
    unittest.main()
