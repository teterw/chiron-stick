"""Unit tests for the grading logic (no hardware needed): python3 -m unittest discover -s tests"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chiron import history, report, win11_cpu  # noqa: E402
from chiron.checks import battery, diskspace, kernel_log, storage, win11  # noqa: E402
from chiron.model import Result, Status, worst  # noqa: E402
from chiron.stress import grade_cpu  # noqa: E402

GB = 1000**3


class Model(unittest.TestCase):
    def test_worst(self):
        self.assertEqual(worst([Status.GREEN, Status.RED, Status.YELLOW]), Status.RED)
        self.assertEqual(worst([Status.NA, Status.NA]), Status.NA)
        self.assertEqual(worst([Status.NA, Status.INFO]), Status.INFO)
        self.assertEqual(worst([]), Status.NA)


class Battery(unittest.TestCase):
    def bat(self, **kw):
        b = {"full": 40.0, "design": 50.0, "now": 20.0, "rate": 10.0, "status": "Full", "capacity_pct": 100, "cycles": 300}
        b.update(kw)
        return b

    def test_health_thresholds(self):
        self.assertEqual(battery.grade_health(85), Status.GREEN)
        self.assertEqual(battery.grade_health(80), Status.GREEN)
        self.assertEqual(battery.grade_health(79.9), Status.YELLOW)
        self.assertEqual(battery.grade_health(59), Status.RED)
        self.assertEqual(battery.grade_health(None), Status.NA)

    def test_cycles(self):
        self.assertEqual(battery.grade_cycles(0), Status.NA)  # not reported
        self.assertEqual(battery.grade_cycles(499), Status.GREEN)
        self.assertEqual(battery.grade_cycles(1000), Status.YELLOW)
        self.assertEqual(battery.grade_cycles(1001), Status.RED)

    def test_runtime_when_discharging(self):
        status, _, ev, params = battery.evaluate(self.bat(status="Discharging", full=29.0), on_ac=False)
        self.assertEqual(status, Status.RED)  # 29/50 = 58%
        self.assertEqual(params["pct"], 58)
        self.assertEqual(params["hours"], 2.9)  # 29 Wh / 10 W

    def test_not_charging_on_ac(self):
        status, summary, _, _ = battery.evaluate(self.bat(full=48.0, status="Not charging", capacity_pct=60), on_ac=True)
        self.assertEqual(status, Status.YELLOW)
        self.assertIn("not charging", summary)


class Storage(unittest.TestCase):
    def nvme(self, **log):
        base = {"critical_warning": 0, "percentage_used": 3, "media_errors": 0, "available_spare": 100,
                "available_spare_threshold": 10}
        base.update(log)
        return {"smart_status": {"passed": True}, "device": {"protocol": "NVMe"}, "nvme_smart_health_information_log": base}

    def ata(self, attrs, passed=True):
        return {"smart_status": {"passed": passed}, "device": {"protocol": "ATA"}, "rotation_rate": 0,
                "ata_smart_attributes": {"table": [{"id": i, "raw": {"value": v}} for i, v in attrs.items()]}}

    def test_nvme(self):
        self.assertEqual(storage.grade_smart(self.nvme(), "nvme")[0], Status.GREEN)
        self.assertEqual(storage.grade_smart(self.nvme(percentage_used=85), "nvme")[0], Status.YELLOW)
        self.assertEqual(storage.grade_smart(self.nvme(percentage_used=101), "nvme")[0], Status.RED)
        self.assertEqual(storage.grade_smart(self.nvme(media_errors=2), "nvme")[0], Status.RED)
        self.assertEqual(storage.grade_smart(self.nvme(critical_warning=4), "nvme")[0], Status.RED)
        self.assertEqual(storage.grade_smart(self.nvme(available_spare=5), "nvme")[0], Status.RED)

    def test_ata(self):
        self.assertEqual(storage.grade_smart(self.ata({5: 0, 197: 0}), "ssd")[0], Status.GREEN)
        self.assertEqual(storage.grade_smart(self.ata({5: 3}), "hdd")[0], Status.YELLOW)
        self.assertEqual(storage.grade_smart(self.ata({5: 11}), "hdd")[0], Status.RED)
        self.assertEqual(storage.grade_smart(self.ata({197: 1}), "hdd")[0], Status.RED)
        self.assertEqual(storage.grade_smart(self.ata({198: 2}), "hdd")[0], Status.RED)
        self.assertEqual(storage.grade_smart(self.ata({199: 7}), "ssd")[0], Status.YELLOW)
        self.assertEqual(storage.grade_smart(self.ata({187: 16}), "ssd")[0], Status.YELLOW)  # old read errors alone
        self.assertEqual(storage.grade_smart(self.ata({}, passed=False), "ssd")[0], Status.RED)

    def test_temperature_and_speed(self):
        self.assertEqual(storage.grade_temperature(54), Status.GREEN)
        self.assertEqual(storage.grade_temperature(70), Status.YELLOW)
        self.assertEqual(storage.grade_temperature(71), Status.RED)
        self.assertEqual(storage.grade_speed(500, "ssd", "sata"), Status.GREEN)
        self.assertEqual(storage.grade_speed(250, "ssd", "sata"), Status.YELLOW)
        self.assertEqual(storage.grade_speed(100, "ssd", "sata"), Status.RED)
        self.assertEqual(storage.grade_speed(100, "ssd", "usb"), Status.INFO)  # USB-limited, not a fault
        self.assertEqual(storage.grade_speed(None, "hdd", None), Status.NA)


class KernelLog(unittest.TestCase):
    LOG = "\n".join([
        "[ 1.0] kernel: blk_update_request: I/O error, dev sdb, sector 1234 op 0x0:(READ)",
        "[ 2.0] kernel: ACPI BIOS Error (bug): Could not resolve symbol",
        "[ 3.0] kernel: pcieport 0000:00:1c.0: AER: Corrected error received",
        "[ 4.0] kernel: I/O error, dev sda, sector 99 (this is the stick itself)",
    ])

    def test_scan_and_own_disk(self):
        found = kernel_log.scan(self.LOG, own_disks=["sda"])
        self.assertEqual(found["disk I/O errors"]["count"], 1)  # the sda line is left out
        self.assertEqual(found["disk I/O errors"]["status"], Status.RED)
        self.assertEqual(found["PCIe errors (corrected)"]["status"], Status.YELLOW)
        self.assertEqual(found["firmware (ACPI) bugs"]["status"], Status.INFO)


class Win11Cpu(unittest.TestCase):
    def test_known_cpus(self):
        cases = {
            "13th Gen Intel(R) Core(TM) i5-13420H": True,
            "AMD Ryzen 5 7500F 6-Core Processor": True,
            "Intel(R) Core(TM) i5-8250U CPU @ 1.60GHz": True,
            "Intel(R) Core(TM) i5-1135G7 @ 2.40GHz": True,
            "Intel(R) Core(TM) i7-7700K CPU @ 4.20GHz": False,
            "AMD Ryzen 5 3400G with Radeon Vega Graphics": False,  # 3000 G models excluded
            "AMD Ryzen 7 3700X 8-Core Processor": True,
            "AMD Ryzen 5 1600 Six-Core Processor": False,
            "Intel(R) Celeron(R) N4020 CPU @ 1.10GHz": True,
            "Intel(R) Core(TM) Ultra 7 155H": True,
            "Intel(R) Pentium(R) Silver N6000 @ 1.10GHz": True,
            "Intel(R) Core(TM) i9-14900K": True,
        }
        data = win11_cpu.load()
        self.assertIsNotNone(data, "chiron/data/win11-cpus.json missing")
        for model, expected in cases.items():
            with self.subTest(model=model):
                self.assertEqual(win11_cpu.check(model, data)[0], expected, win11_cpu.check(model, data)[1])

    def test_evaluate(self):
        ok = (True, "fine")
        self.assertEqual(win11.evaluate(2, True, True, ok, 16, 512 * GB)[0], Status.GREEN)
        self.assertEqual(win11.evaluate(None, True, True, ok, 16, 512 * GB)[0], Status.RED)
        self.assertEqual(win11.evaluate(2, False, None, ok, 16, 512 * GB)[0], Status.YELLOW)
        self.assertEqual(win11.evaluate(2, True, True, (False, "old"), 16, 512 * GB)[0], Status.RED)
        self.assertEqual(win11.evaluate(2, True, True, ok, 3.5, 512 * GB)[0], Status.RED)
        self.assertEqual(win11.evaluate(2, True, True, ok, 8, 32 * GB)[0], Status.RED)


class DiskSpace(unittest.TestCase):
    def test_free_space(self):
        self.assertEqual(diskspace.grade_free(100 * GB, 500 * GB), Status.GREEN)   # 20%
        self.assertEqual(diskspace.grade_free(75 * GB, 500 * GB), Status.YELLOW)   # 15%
        self.assertEqual(diskspace.grade_free(40 * GB, 500 * GB), Status.RED)      # 8%
        self.assertEqual(diskspace.grade_free(9 * GB, 60 * GB), Status.RED)        # 15% but < 10 GB


class Stress(unittest.TestCase):
    def test_grade_cpu(self):
        self.assertEqual(grade_cpu(80, 100, 3, 0, None), Status.GREEN)
        self.assertEqual(grade_cpu(99, 100, 5, 0, None), Status.YELLOW)   # at the limit: by design on thin laptops
        self.assertEqual(grade_cpu(85, 100, 15, 0, None), Status.YELLOW)
        self.assertEqual(grade_cpu(85, 100, 30, 0, None), Status.RED)
        self.assertEqual(grade_cpu(101, 100, 0, 0, None), Status.RED)
        self.assertEqual(grade_cpu(90, 100, 0, 0, "temp"), Status.RED)
        self.assertEqual(grade_cpu(None, 100, None, 0, None), Status.INFO)  # VM: nothing to grade


class HistoryAndReport(unittest.TestCase):
    def test_compare_only_current_measurements(self):
        before = {"CPU max °C under load": 96, "battery: health %": 70}
        after = {"CPU max °C under load": 78}
        self.assertEqual(history.compare(before, after),
                         [{"name": "CPU max °C under load", "before": 96, "after": 78}])

    def test_write_all(self):
        results = [Result("battery", "Battery BAT0", Status.YELLOW, "health 70%", {"health_pct": 70},
                          ("battery.yellow", {"pct": 70, "hours": None})).to_dict(),
                   Result("storage", "Disk", Status.GREEN, "healthy", {}, ("storage.green", {"model": "X", "size": "1 TB"})).to_dict()]
        rep = {"chiron": "test", "created": "2026-10-04T10:00:00+07:00", "fingerprint": "abc",
               "machine": {"sys_vendor": "Acme", "product_name": "Book"}, "results": results}
        with tempfile.TemporaryDirectory() as d:
            report.write_all(rep, Path(d))
            self.assertEqual(rep["overall"], "yellow")
            owner = (Path(d) / "owner-summary.html").read_text(encoding="utf-8")
            self.assertIn("แบตเตอรี่เก็บไฟได้ 70%", owner)
            self.assertIn("The battery holds 70%", owner)
            for f in ("report.json", "report.md", "report.html"):
                self.assertTrue((Path(d) / f).exists())

    def test_catalogs_have_the_same_keys(self):
        en, th = report.catalog("en"), report.catalog("th")
        self.assertEqual(set(en), set(th))


if __name__ == "__main__":
    unittest.main()
