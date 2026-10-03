#!/usr/bin/env python3
"""Refresh chiron/data/win11-cpus.json from Microsoft's official Windows 11 supported-processor
lists (the rule Windows itself applies). Run on a machine with internet, then commit the JSON.
Usage: tools/update-win11-cpus.py [release]   (default: 25h2)"""
import datetime
import html
import json
import re
import sys
import urllib.request
from pathlib import Path

RELEASE = sys.argv[1] if len(sys.argv) > 1 else "25h2"
URL = "https://learn.microsoft.com/en-us/windows-hardware/design/minimum/supported/windows-11-{}-supported-{}-processors"
OUT = Path(__file__).resolve().parent.parent / "chiron" / "data" / "win11-cpus.json"


def clean(cell):
    text = html.unescape(re.sub(r"<[^>]+>", "", cell)).replace("®", "").replace("™", "")
    return re.sub(r"\s+", " ", text).strip()


def table(vendor):
    url = URL.format(RELEASE, vendor)
    with urllib.request.urlopen(url, timeout=60) as r:
        page = r.read().decode("utf-8")
    rows = []
    for tr in re.findall(r"<tr>(.*?)</tr>", page, re.S)[1:]:
        cells = [clean(c) for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", tr, re.S)]
        if len(cells) >= 3:
            rows.append({"product": cells[1], "series": cells[2], "exception": cells[3] if len(cells) > 3 else ""})
    if not rows:
        sys.exit(f"no rows found at {url}: did the page layout change?")
    return url, rows


data = {"release": RELEASE.upper(), "fetched": datetime.date.today().isoformat(),
        "note": "Microsoft's official Windows 11 supported processor lists (by series).", "sources": [], "vendors": {}}
for vendor in ("intel", "amd"):
    url, rows = table(vendor)
    data["sources"].append(url)
    data["vendors"][vendor] = rows
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
print(f"wrote {OUT}: " + ", ".join(f"{v} {len(r)} series" for v, r in data["vendors"].items()))
