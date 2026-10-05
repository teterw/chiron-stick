"""Tests for the spec sheet (chiron/specs.py): parsers fed with captured tool output."""
import json
import unittest

from chiron import specs

DMI_17 = """# dmidecode 3.5
Handle 0x0012, DMI type 17, 92 bytes
Memory Device
	Size: 8 GB
	Form Factor: SODIMM
	Locator: DIMM A
	Type: DDR4
	Speed: 3200 MT/s
	Manufacturer: Samsung
	Part Number: M471A1K43DB1-CWE
	Configured Memory Speed: 3200 MT/s

Handle 0x0013, DMI type 17, 92 bytes
Memory Device
	Size: No Module Installed
	Form Factor: SODIMM
	Locator: DIMM B
	Type: Unknown
	Speed: Unknown

Handle 0x0014, DMI type 17, 92 bytes
Memory Device
	Size: 8192 MB
	Form Factor: Row Of Chips
	Locator: Onboard
	Type: DDR4
	Speed: 3200 MT/s
	Manufacturer: Micron
	Part Number: MT40A1G16
"""
DMI_16 = """Handle 0x0011, DMI type 16, 23 bytes
Physical Memory Array
	Location: System Board Or Motherboard
	Maximum Capacity: 32 GB
	Number Of Devices: 3
"""
LSCPU = json.dumps({"lscpu": [
    {"field": "Architecture:", "data": "x86_64"},
    {"field": "Model name:", "data": "13th Gen Intel(R) Core(TM) i5-13420H"},
    {"field": "CPU(s):", "data": "12"},
    {"field": "Thread(s) per core:", "data": "2"},
    {"field": "Core(s) per socket:", "data": "8"},
    {"field": "Socket(s):", "data": "1"},
    {"field": "CPU max MHz:", "data": "4600.0000"},
    {"field": "L3 cache:", "data": "12 MiB (1 instance)"}]})


def edid(maker="AUO", product=0x238D, mm=(344, 194), res=(1920, 1080), name="B156HAN02.1"):
    e = bytearray(128)
    e[0:8] = b"\x00\xff\xff\xff\xff\xff\xff\x00"
    code = sum((ord(c) - 64) << shift for c, shift in zip(maker, (10, 5, 0)))
    e[8], e[9] = code >> 8, code & 0xFF
    e[10], e[11] = product & 0xFF, product >> 8
    e[21], e[22] = mm[0] // 10, mm[1] // 10
    d = 54  # preferred timing
    e[d], e[d + 1] = 0x56, 0x5E
    e[d + 2], e[d + 4] = res[0] & 0xFF, (res[0] >> 8) << 4
    e[d + 5], e[d + 7] = res[1] & 0xFF, (res[1] >> 8) << 4
    e[d + 12], e[d + 13], e[d + 14] = mm[0] & 0xFF, mm[1] & 0xFF, ((mm[0] >> 8) << 4) | (mm[1] >> 8)
    n = 72  # a monitor-name descriptor
    e[n:n + 5] = b"\x00\x00\x00\xfc\x00"
    e[n + 5:n + 18] = (name + "\n").encode().ljust(13, b" ")[:13]
    return bytes(e)


class Parsers(unittest.TestCase):
    def test_memory_slots(self):
        m = specs.parse_memory(DMI_17, DMI_16)
        self.assertEqual(m["slots_total"], 3)
        self.assertEqual(m["slots_used"], 2)
        self.assertEqual(m["max_gb"], 32)
        self.assertEqual(m["total_gb"], 16)
        first = m["sticks"][0]
        self.assertEqual((first["slot"], first["size_gb"], first["type"], first["speed"], first["form"]),
                         ("DIMM A", 8, "DDR4", "3200 MT/s", "SODIMM"))
        self.assertEqual(m["sticks"][1]["form"], "soldered", "Row Of Chips is memory soldered to the board")
        self.assertEqual(m["upgrade"], "DDR4 SODIMM 3200 MT/s")

    def test_cpu(self):
        c = specs.parse_lscpu(LSCPU)
        self.assertEqual(c["model"], "Intel Core i5-13420H")
        self.assertEqual((c["cores"], c["threads"]), (8, 12))
        self.assertEqual(c["max_ghz"], 4.6)
        self.assertEqual(c["l3"], "12 MiB")

    def test_screen(self):
        s = specs.parse_edid(edid())
        self.assertEqual(s["maker"], "AUO")
        self.assertEqual(s["model"], "B156HAN02.1")
        self.assertEqual(s["resolution"], "1920×1080")
        self.assertAlmostEqual(s["inches"], 15.6, delta=0.1)
        self.assertIsNone(specs.parse_edid(b"\x00" * 10), "too short or not an EDID")

    def test_panel_model_in_free_text(self):
        e = bytearray(edid(name="x"))
        e[72:90] = b"\x00\x00\x00\xfe\x00" + b"AUO\n".ljust(13, b" ")
        e[90:108] = b"\x00\x00\x00\xfe\x00" + b"B156HAN08.4\n".ljust(13, b" ")
        self.assertEqual(specs.parse_edid(bytes(e))["model"], "B156HAN08.4")

    def test_device_names(self):
        self.assertEqual(specs.tidy("Intel Corporation Raptor Lake-P [UHD Graphics] [8086:a7a8] (rev 04)"),
                         "Intel Raptor Lake-P UHD Graphics")

    def test_sheet_lines_have_no_serials(self):
        sheet = {"system": {"maker": "Acer", "model": "Aspire", "bios": "V1.10 (2023-05-01)"},
                 "memory": specs.parse_memory(DMI_17, DMI_16), "cpu": specs.parse_lscpu(LSCPU)}
        lines = specs.lines(sheet)
        text = json.dumps(lines)
        self.assertIn("Intel Core i5-13420H", text)
        self.assertIn("2 of 3 slots used", text)
        self.assertNotIn("serial", text.lower())


class InTheReport(unittest.TestCase):
    def test_spec_sheet_page_and_ram_part(self):
        import tempfile
        from pathlib import Path
        from chiron import report
        sheet = {"system": {"maker": "Acer", "model": "Aspire"}, "memory": specs.parse_memory(DMI_17, DMI_16)}
        bad_ram = {"area": "ram_test", "title": "RAM test", "status": "red", "summary": "errors", "evidence": {}}
        rep = {"chiron": "t", "created": "2026-10-05T15:00:00+07:00", "machine": {"sys_vendor": "Acer", "product_name": "Aspire"},
               "results": [bad_ram], "specs": sheet}
        with tempfile.TemporaryDirectory() as tmp:
            report.write_all(rep, Path(tmp))
            page = (Path(tmp) / "spec-sheet.html").read_text()
            self.assertIn("2 of 3 slots used", page)
            self.assertIn("Spec sheet", (Path(tmp) / "report.html").read_text())
        self.assertEqual(rep["todo"][0]["part"], "RAM stick: DDR4 SODIMM 3200 MT/s, same size as the faulty one")


if __name__ == "__main__":
    unittest.main()
