"""Tests for "What to do" (chiron/advice.py): a next step and the part to look for, per finding."""
import unittest

from chiron import advice


def res(area, status, summary="", **ev):
    return {"area": area, "title": area.title(), "status": status, "summary": summary, "evidence": ev}


class Advice(unittest.TestCase):
    def test_green_and_info_need_nothing(self):
        self.assertIsNone(advice.todo_for(res("battery", "green")))
        self.assertIsNone(advice.todo_for(res("system", "info")))
        self.assertIsNone(advice.todo_for(res("battery", "n/a")))

    def test_worn_battery_names_the_part(self):
        t = advice.todo_for(res("battery", "red", manufacturer="SMP", model="AP18C8K", technology="Li-ion", unit="Wh",
                                design=48.0))
        self.assertIn("Replace the battery", t["action"])
        self.assertEqual(t["part"], "Battery SMP AP18C8K · Li-ion · 48 Wh")
        y = advice.todo_for(res("battery", "yellow", model="AP18C8K"))
        self.assertIn("plan", y["action"].lower())

    def test_failing_drive_back_up_first(self):
        t = advice.todo_for(res("storage", "red", model="WDC WDS120G2G0B", size_bytes=120_040_980_480, **{"class": "ssd"},
                                transport="sata"))
        self.assertTrue(t["action"].startswith("Back up"))
        self.assertIn("SATA SSD", t["part"])
        self.assertIn("120 GB or larger", t["part"])
        n = advice.todo_for(res("storage", "red", size_bytes=512_110_190_592, **{"class": "nvme"}))
        self.assertEqual(n["part"], "M.2 NVMe SSD, 512 GB or larger")
        self.assertEqual([advice.nominal(b) for b in (240_057_409_536, 1_000_204_886_016, 2_000_398_934_016)],
                         ["240 GB", "1 TB", "2 TB"])
        self.assertIsNone(advice.todo_for(res("storage", "red", **{"class": "ssd"}, transport="usb"))["part"],
                          "an external drive isn't part of the computer")

    def test_overheating(self):
        t = advice.todo_for(res("cpu_load", "red", max_temp_c=100, tjmax_c=100))
        self.assertIn("vents", t["action"])
        self.assertIn("thermal paste", t["part"].lower())

    def test_windows11_reasons(self):
        t = advice.todo_for(res("win11", "red", reasons=["TPM 2.0 missing or off", "Secure Boot off"]))
        self.assertIn("TPM", t["action"])
        self.assertIn("Secure Boot", t["action"])

    def test_every_area_has_something_to_say(self):
        for area in ("battery", "storage", "diskspace", "memory", "ram_test", "cpu", "cpu_load", "fans", "gpu",
                     "kernel_log", "devices", "win11", "secureboot_certs", "firmware", "sensors"):
            t = advice.todo_for(res(area, "red", "something"))
            self.assertTrue(t and t["action"], area)

    def test_list_puts_red_first(self):
        todo = advice.todo([res("diskspace", "yellow"), res("storage", "red"), res("battery", "green")])
        self.assertEqual([t["area"] for t in todo], ["storage", "diskspace"])


class InTheReport(unittest.TestCase):
    def test_report_and_owner_summary(self):
        import json
        import tempfile
        from pathlib import Path
        from chiron import report
        bat = res("battery", "red", "health 52%", manufacturer="SMP", model="AP18C8K", technology="Li-ion", unit="Wh", design=48.0)
        bat["owner"] = {"key": "battery.red", "params": {"pct": 52}}
        rep = {"chiron": "test", "created": "2026-10-05T15:00:00+07:00", "machine": {"sys_vendor": "Acer", "product_name": "Aspire"},
               "results": [bat, res("memory", "green", "16 GB")]}
        with tempfile.TemporaryDirectory() as tmp:
            report.write_all(rep, Path(tmp))
            saved = json.loads((Path(tmp) / "report.json").read_text())
            self.assertEqual(saved["todo"][0]["area"], "battery")
            self.assertIn("What to do", (Path(tmp) / "report.html").read_text())
            owner = (Path(tmp) / "owner-summary.html").read_text()
            self.assertIn("Battery SMP AP18C8K", owner)
            self.assertIn("อะไหล่", owner)


if __name__ == "__main__":
    unittest.main()
