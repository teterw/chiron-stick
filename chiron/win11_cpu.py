"""Is this CPU on Microsoft's Windows 11 supported-processor list? Since 24H2 the list names
series ("13th Generation Core i5 Processors", "Ryzen 7000 Series"), so we work out which series
this CPU belongs to and look it up in data/win11-cpus.json (refresh: tools/update-win11-cpus.py)."""
import json
import re
from pathlib import Path

DATA = Path(__file__).parent / "data" / "win11-cpus.json"
ORD = {8: "8th", 9: "9th", 10: "10th", 11: "11th", 12: "12th", 13: "13th", 14: "14th"}


def load():
    try:
        return json.loads(DATA.read_text())
    except (OSError, ValueError):
        return None


def normalize(model):
    m = re.sub(r"\((R|TM|tm)\)|[®™]", "", model)
    m = re.sub(r"@.*$|\bCPU\b|\bProcessor\b|\d+-Core|with Radeon.*$|w/ Radeon.*$", "", m)
    return re.sub(r"\s+", " ", m).strip()


def intel_candidates(m):
    """(product, series) names this Intel CPU could be listed under."""
    c = []
    x = re.search(r"\bCore i([3579])-(\d{4,5})", m)
    if x:
        fam, num = x.group(1), x.group(2)
        gen = int(num[:2]) if len(num) == 5 or num[0] == "1" else int(num[0])  # 1035G1/1135G7/1235U -> 10/11/12
        if gen == 14:
            c.append(("Intel Core", f"Core i{fam} processors (14th Generation)"))
        elif gen in ORD:
            c.append(("Intel Core", f"{ORD[gen]} Generation Core i{fam} Processors"))
        else:  # 7th generation and older: placed, but not on the list -> "not supported"
            c.append(("Intel Core", f"{gen}th Generation Core i{fam} Processors"))
    if re.search(r"\bCore i3-N3\d\d", m):
        c.append(("Intel Core", "Core Processor N300 Series"))
    x = re.search(r"\bCore m\d-(\d)", m)
    if x and x.group(1) == "8":
        c.append(("Intel Core", "8th Generation Core m Processors"))
    x = re.search(r"\bCore Ultra [3579] (\d)\d\d", m)
    if x:
        c.append(("Intel Core Ultra", f"Core Ultra Processors (Series {x.group(1)})"))
    x = re.search(r"\bCore [357] ([12])\d\d[A-Z]*\b", m)
    if x:
        c.append(("Intel Core", f"Core Processors (Series {x.group(1)})"))
    x = re.search(r"\bCeleron (?:\w+ )?([GJN]?)(\d)\d{3}", m)
    if x:
        c.append(("Intel Celeron", f"Celeron {x.group(1)}{x.group(2)}000 Series"))
    x = re.search(r"\bPentium (?:(Gold|Silver) )?([GJN]?)(\d)(\d)\d\d([UY]?)", m)
    if x:
        tier, letter, d1, d2, suf = x.groups()
        tier = f"{tier} " if tier else ""
        c.append(("Intel Pentium", f"Pentium {tier}{letter}{d1}000{suf} Series"))
        c.append(("Intel Pentium", f"Pentium {d1}{d2}00 Series"))
    x = re.search(r"\bIntel (N|U)(\d{2,3})\b", m)
    if x:
        letter, num = x.groups()
        c.append(("Intel Processor", f"{letter}{num[0]}{'0' * (len(num) - 1)} Series"))
        c.append(("Intel Processor", f"{letter}{num[0]}{'0' * (len(num) - 1)} series"))
    if re.search(r"\bIntel 3\d\d\b", m):
        c.append(("Intel Processor", "Intel 300 Processor for Desktop"))
    if re.search(r"\bAtom\S* [xX]7\d{3}", m):
        c.append(("Intel Atom", "Atom X7000 Series"))
    x = re.search(r"\bXeon\S* ([WwEeDd])\d?-(\d{4,5})([A-Z]*)", m)
    if x:
        letter, num, suf = x.group(1).upper(), x.group(2), x.group(3)
        if len(num) == 5:
            c.append(("Intel Xeon", f"Xeon {letter}-{num[:2]}000{suf[:1]} Series"))
        else:
            c.append(("Intel Xeon", f"Xeon {letter}-{num[:2]}00 Series"))
    if re.search(r"\bXeon\S* (Bronze|Silver|Gold|Platinum)\b", m):
        c.append(("Intel Xeon", "Xeon Scalable Processors"))
    return c


def amd_candidates(m):
    c = []
    x = re.search(r"\bThreadripper (PRO )?(\d)\d{3}(WX)?", m)
    if x:
        if x.group(1):
            c.append(("Ryzen Threadripper PRO", f"{x.group(2)}000 WX-Series"))
        else:
            c.append(("Ryzen Threadripper", f"{x.group(2)}000 Series"))
        return c
    if re.search(r"\bRyzen AI Max\+? \d{3}", m):
        return [("Ryzen", "AI Max 300 Series")]
    if re.search(r"\bRyzen AI Z2 Extreme", m):
        return [("Ryzen", "AI Z2 Extreme")]
    if re.search(r"\bRyzen AI \d+ (HX )?3\d\d", m):
        return [("Ryzen", "AI 300 Series")]
    x = re.search(r"\bRyzen Z([12])\b", m)
    if x:
        return [("Ryzen", f"Z{x.group(1)} Series")]
    x = re.search(r"\bRyzen \d+ (PRO )?(\d{2,4})([A-Z]*)\b", m)
    if x:
        product = "Ryzen PRO" if x.group(1) else "Ryzen"
        num = x.group(2)
        series = f"{num[0]}{'0' * (len(num) - 1)} Series"
        c.append((product, series, x.group(3)))
    x = re.search(r"\bEPYC (\d)\d\d(\d)", m)
    if x:
        c.append(("EPYC", f"{x.group(1)}00{x.group(2)} Series"))
    x = re.search(r"\bAthlon (?:\w+ )?7\d{3}U\b", m)
    if x:
        c.append(("Athlon", "7000 U Series"))
    return c


def check(model, data=None):
    """(supported: True/False/None, explanation). None = can't tell (unknown CPU or no list)."""
    data = data or load()
    if not data:
        return None, "Microsoft's CPU list isn't available on this stick"
    m = normalize(model)
    vendor = "amd" if "AMD" in m else "intel" if "Intel" in m else None
    if not vendor:
        return None, f"unknown CPU vendor ({model})"
    rows = data["vendors"][vendor]
    cands = amd_candidates(m) if vendor == "amd" else intel_candidates(m)
    for cand in cands:
        product, series = cand[0], cand[1]
        suffix = cand[2] if len(cand) > 2 else ""
        for r in rows:
            if r["product"].lower() == product.lower() and r["series"].lower() == series.lower():
                if r["exception"] == "G & GE" and suffix in ("G", "GE"):
                    return False, f"{product} {series}, but {suffix} models are excluded (Microsoft's list, {data['release']})"
                return True, f"{product} {series} (Microsoft's list, {data['release']})"
    if cands:
        return False, f"not on Microsoft's Windows 11 list ({data['release']}): {m}"
    return None, f"couldn't place this CPU in Microsoft's list: {m}"
