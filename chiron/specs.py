"""The spec sheet (Tete picked it 2026-10-05): everything inside the computer on one page, for
upgrades and quotes: CPU, every RAM stick and the free slots, disks, graphics, the built-in screen,
the battery, network, audio and camera. Serial numbers and MAC addresses are left out on purpose.
collect(ctx) runs as root during a check; the parsers take captured tool output so they can be tested."""
import json
import math
import re
from pathlib import Path

from chiron.advice import nominal
from chiron.util import read, sh


# ---------------------------------------------------------------- parsers

def _gb(text):
    """'8 GB' / '8192 MB' / '1 TB' -> GB as a number, or None."""
    m = re.match(r"(\d+(?:\.\d+)?)\s*(KB|MB|GB|TB)", text or "")
    if not m:
        return None
    v = float(m.group(1)) * {"KB": 1 / 1048576, "MB": 1 / 1024, "GB": 1, "TB": 1024}[m.group(2)]
    return int(v) if v == int(v) else round(v, 1)


def parse_memory(dmi17, dmi16=""):
    """Every memory slot from dmidecode type 17 (+ the board's maximum from type 16)."""
    slots, cur = [], None
    for line in dmi17.splitlines():
        if line.strip() == "Memory Device":
            cur = {}
            slots.append(cur)
        elif cur is not None and ":" in line:
            k, v = (x.strip() for x in line.split(":", 1))
            cur[k] = v
    sticks = []
    for d in slots:
        size = _gb(d.get("Size", ""))
        if not size:
            continue
        form = d.get("Form Factor", "")
        sticks.append({"slot": d.get("Locator") or d.get("Bank Locator") or "?", "size_gb": size,
                       "type": d.get("Type") if d.get("Type") not in (None, "Unknown", "Other") else None,
                       "speed": d.get("Speed") if d.get("Speed") not in (None, "Unknown") else None,
                       "form": "soldered" if form == "Row Of Chips" else form or None,
                       "maker": d.get("Manufacturer") if d.get("Manufacturer") not in (None, "Unknown", "Not Specified") else None,
                       "part": (d.get("Part Number") or "").strip() or None})
    max_gb = None
    for line in dmi16.splitlines():
        if "Maximum Capacity:" in line:
            max_gb = _gb(line.split(":", 1)[1].strip())
    removable = [s for s in sticks if s["form"] != "soldered"]
    ref = removable[0] if removable else (sticks[0] if sticks else None)
    upgrade = " ".join(x for x in (ref.get("type"), ref.get("form") if ref and ref.get("form") != "soldered" else None,
                                   ref.get("speed")) if x) if ref else None
    sockets = [d for d in slots if d.get("Form Factor") != "Row Of Chips"]
    return {"total_gb": sum(s["size_gb"] for s in sticks), "slots_total": len(slots),
            "slots_used": len(sticks), "slots_free": sum(1 for d in sockets if not _gb(d.get("Size", ""))),
            "max_gb": max_gb, "sticks": sticks, "upgrade": upgrade or None}


def parse_lscpu(text):
    try:
        rows = {r["field"].rstrip(":"): r.get("data") for r in json.loads(text)["lscpu"]}
    except (ValueError, KeyError, TypeError):
        return {}
    model = rows.get("Model name") or ""
    for junk in ("(R)", "(TM)", " CPU", "Processor", "13th Gen ", "12th Gen ", "11th Gen ", "14th Gen "):
        model = model.replace(junk, "")
    model = " ".join(model.split("@")[0].split())

    def num(k):
        try:
            return int(float(rows.get(k) or ""))
        except ValueError:
            return None
    threads, per_core = num("CPU(s)"), num("Thread(s) per core")
    cores = (num("Core(s) per socket") or 0) * (num("Socket(s)") or 1) or (threads // per_core if threads and per_core else None)
    mhz = num("CPU max MHz")
    l3 = (rows.get("L3 cache") or rows.get("L3") or "").split("(")[0].strip() or None
    return {"model": model or None, "cores": cores, "threads": threads,
            "max_ghz": round(mhz / 1000, 1) if mhz else None, "l3": l3, "arch": rows.get("Architecture")}


def parse_edid(data):
    """A screen's maker, model, size and native resolution from its EDID."""
    if len(data) < 128 or data[:8] != b"\x00\xff\xff\xff\xff\xff\xff\x00":
        return None
    code = (data[8] << 8) | data[9]
    maker = "".join(chr(((code >> s) & 0x1F) + 64) for s in (10, 5, 0))
    model, strings = None, []
    for off in (54, 72, 90, 108):
        block = data[off:off + 18]
        if block[0:2] == b"\x00\x00" and block[3] in (0xFC, 0xFE):
            text = block[5:18].split(b"\n")[0].decode("ascii", "replace").strip()
            if block[3] == 0xFC:
                model = text or model
            elif text:
                strings.append(text)
    if not model and strings:  # laptop panels: the last free-text field is usually the panel model
        model = strings[-1]
    d = data[54:72]
    w = h = None
    if d[0] or d[1]:
        w, h = d[2] | ((d[4] & 0xF0) << 4), d[5] | ((d[7] & 0xF0) << 4)
        mm_w, mm_h = d[12] | ((d[14] & 0xF0) << 4), d[13] | ((d[14] & 0x0F) << 8)
    else:
        mm_w = mm_h = 0
    if not (mm_w and mm_h):
        mm_w, mm_h = data[21] * 10, data[22] * 10
    inches = round(math.hypot(mm_w, mm_h) / 25.4, 1) if mm_w and mm_h else None
    return {"maker": maker, "model": model, "product": f"{data[10] | (data[11] << 8):04X}",
            "resolution": f"{w}×{h}" if w and h else None, "inches": inches}


def tidy(name):
    """'Intel Corporation Raptor Lake-P [UHD Graphics] [8086:a7a8] (rev 04)' -> 'Intel Raptor Lake-P UHD Graphics'."""
    name = re.sub(r"\s*\[[0-9a-f]{4}:[0-9a-f]{4}\]|\s*\(rev [0-9a-f]+\)", "", name)
    name = re.sub(r"\b(Corporation|Corp\.|Co\., Ltd\.|Inc\.|Semiconductor Co\.|Technology Co\.)", "", name)
    name = name.replace("[", "").replace("]", "")
    return " ".join(name.split())


# ---------------------------------------------------------------- collecting (root, during a check)

def collect(ctx=None):
    from chiron.checks.battery import PS, read_battery
    from chiron.checks.devices import pci_devices, pci_kind
    from chiron.checks.system import identity
    own = getattr(ctx, "own", set()) or set()
    i = identity()
    sheet = {"system": {"maker": i.get("sys_vendor"), "model": i.get("product_name"),
                        "version": i.get("product_version") if i.get("product_version") not in ("", "None", None) else None,
                        "board": " ".join(x for x in (i.get("board_vendor"), i.get("board_name")) if x) or None,
                        "bios": f"{i.get('bios_vendor') or ''} {i.get('bios_version') or ''} ({i.get('bios_date') or '?'})".strip()}}
    rc, out, _ = sh(["lscpu", "-J"])
    sheet["cpu"] = parse_lscpu(out) if rc == 0 else {}
    rc17, d17, _ = sh(["dmidecode", "-t", "17"])
    rc16, d16, _ = sh(["dmidecode", "-t", "16"])
    if rc17 == 0:
        sheet["memory"] = parse_memory(d17, d16 if rc16 == 0 else "")
    rc, out, _ = sh(["lsblk", "-J", "-b", "-d", "-o", "NAME,MODEL,SIZE,TRAN,ROTA,TYPE"])
    disks = []
    if rc == 0:
        for d in json.loads(out).get("blockdevices", []):
            if d.get("type") != "disk" or d["name"] in own or d["name"].startswith(("zram", "loop")) or not d.get("size"):
                continue
            kind = "NVMe SSD" if d["name"].startswith("nvme") else ("HDD" if d.get("rota") in (True, "1", 1) else "SSD")
            disks.append({"model": (d.get("model") or "").strip() or "Disk", "size": nominal(int(d["size"])),
                          "kind": kind, "interface": d.get("tran") or ("nvme" if kind == "NVMe SSD" else None)})
    sheet["storage"] = disks
    pci = [{**p, "name": tidy(p["name"])} for p in pci_devices()]
    sheet["graphics"] = [{"name": p["name"], "driver": p["driver"]} for p in pci if pci_kind(p["code"]) == "graphics"]
    sheet["network"] = [{"name": p["name"]} for p in pci if pci_kind(p["code"]) == "network"]
    sheet["audio"] = [{"name": p["name"]} for p in pci if pci_kind(p["code"]) == "audio"]
    screens = []
    for e in sorted(Path("/sys/class/drm").glob("card*-*/edid")):
        try:
            data = e.read_bytes()
        except OSError:
            continue
        s = parse_edid(data)
        if s:
            s["connector"] = e.parent.name.split("-", 1)[1]
            s["built_in"] = s["connector"].startswith(("eDP", "LVDS", "DSI"))
            screens.append(s)
    sheet["screens"] = screens
    sheet["battery"] = [b for b in (read_battery(p) for p in sorted(PS.glob("BAT*")))]
    sheet["camera"] = [read(p / "name") for p in sorted(Path("/sys/class/video4linux").glob("video*"))
                       if read(p / "index") in ("0", None)]
    return sheet


# ---------------------------------------------------------------- one page of lines

def lines(sheet):
    """[(section, [(label, value), …]), …] for the report, the printable page and the doctor."""
    out = []
    sysi = sheet.get("system") or {}
    rows = [("Computer", " ".join(x for x in (sysi.get("maker"), sysi.get("model")) if x)),
            ("Board", sysi.get("board")), ("BIOS", sysi.get("bios"))]
    out.append(("System", rows))
    c = sheet.get("cpu") or {}
    if c:
        rows = [("Processor", c.get("model")),
                ("Cores", f"{c['cores']} cores, {c['threads']} threads" if c.get("cores") and c.get("threads") else None),
                ("Top speed", f"{c['max_ghz']} GHz" if c.get("max_ghz") else None), ("L3 cache", c.get("l3"))]
        out.append(("Processor", rows))
    m = sheet.get("memory")
    if m:
        rows = [("Installed", f"{m['total_gb']} GB · {m['slots_used']} of {m['slots_total']} slots used"
                 + (f" · up to {m['max_gb']} GB" if m.get("max_gb") else ""))]
        for s in m["sticks"]:
            rows.append((s["slot"], " · ".join(x for x in (f"{s['size_gb']} GB", s.get("type"), s.get("form"), s.get("speed"),
                                                            " ".join(y for y in (s.get("maker"), s.get("part")) if y) or None) if x)))
        if m.get("upgrade"):
            rows.append(("To add RAM", f"{m['upgrade']} · {m['slots_free']} free slot(s)" if m.get("slots_free") else
                         f"{m['upgrade']} · no free slot: replace a stick"))
        out.append(("Memory", rows))
    if sheet.get("storage"):
        out.append(("Storage", [(d["kind"], f"{d['model']} · {d['size']}" + (f" · {d['interface']}" if d.get("interface") else ""))
                                for d in sheet["storage"]]))
    if sheet.get("graphics"):
        out.append(("Graphics", [("GPU", g["name"] + (f" (driver {g['driver']})" if g.get("driver") else " (no driver here)"))
                                 for g in sheet["graphics"]]))
    if sheet.get("screens"):
        out.append(("Screen", [("Built-in" if s.get("built_in") else s.get("connector", "Screen"),
                                " · ".join(x for x in (f"{s['inches']}-inch" if s.get("inches") else None, s.get("resolution"),
                                                       " ".join(y for y in (s.get("maker"), s.get("model")) if y)) if x))
                               for s in sheet["screens"]]))
    bats = [b for b in sheet.get("battery", []) if b]
    if bats:
        rows = []
        for b in bats:
            cap = None
            if b.get("full") and b.get("design"):
                fmt = ".0f" if b.get("unit") == "Wh" else ".2f"
                cap = (f"{b['full']:{fmt}} of {b['design']:{fmt}} {b.get('unit', 'Wh')} design"
                       f" ({round(100 * b['full'] / b['design'])}%)")
            rows.append(("Battery", " · ".join(x for x in (" ".join(y for y in (b.get("manufacturer"), b.get("model")) if y) or None,
                                                          b.get("technology"), cap,
                                                          f"{b['cycles']} cycles" if b.get("cycles") else None) if x)))
        out.append(("Battery", rows))
    other = [("Network", n["name"]) for n in sheet.get("network", [])] + [("Audio", a["name"]) for a in sheet.get("audio", [])] \
        + [("Camera", c) for c in sheet.get("camera", []) if c]
    if other:
        out.append(("Other devices", other))
    return [(sec, [(k, v) for k, v in rows if v]) for sec, rows in out if any(v for _k, v in rows)]
