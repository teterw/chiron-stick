"""Report files: report.json (everything), report.md and report.html (technical), and
owner-summary.html (one printable page in Thai and English for a non-technical owner).
Verdict colours are fixed here and never come from the desktop theme (CLAUDE.md decision 10)."""
import html
import json
from pathlib import Path

from chiron.advice import todo
from chiron.model import Status, worst

COLORS = {"green": "#1e8e3e", "yellow": "#e37400", "red": "#d93025", "n/a": "#80868b", "info": "#5f6368"}
DOT = {"green": "🟢", "yellow": "🟡", "red": "🔴", "n/a": "⚪", "info": "ℹ️"}
I18N = Path(__file__).parent / "i18n"
# Owner summary: one line per message key prefix, in this order
OWNER_ORDER = ["battery", "storage", "diskspace", "memory", "ram_test", "cpu_idle", "cpu_load", "fans", "gpu",
               "kernel_log", "devices", "win11", "sbcerts", "firmware"]


def catalog(lang):
    return json.loads((I18N / f"{lang}.json").read_text(encoding="utf-8"))


class _Blank(dict):
    def __missing__(self, key):
        return "?"


def message(cat, key, params):
    text = cat.get(key) or cat.get(key.rsplit(".", 1)[0] + ".unknown") or key
    return text.format_map(_Blank({k: ("?" if v is None else v) for k, v in (params or {}).items()}))


def overall(results):
    graded = [Status(r["status"]) for r in results if r["status"] in ("green", "yellow", "red")]
    return worst(graded, default=Status.GREEN).value


def machine_name(report):
    m = report.get("machine", {})
    return " ".join(x for x in (m.get("sys_vendor"), m.get("product_name")) if x) or "Unknown computer"


def _fmt(v):
    if isinstance(v, float):
        return f"{v:g}"
    if isinstance(v, (list, dict)):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def write_json(report, folder):
    (folder / "report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def write_markdown(report, folder):
    o = report["overall"]
    lines = [f"# Chiron Stick report: {machine_name(report)}", "",
             f"Created {report['created']} with Chiron {report['chiron']}", "",
             f"**Overall: {DOT[o]} {o}**", ""]
    if report.get("todo"):
        lines += ["## What to do", ""]
        lines += [f"- {DOT[t['status']]} **{t['title']}**: {t['action']}" + (f" Part: {t['part']}." if t.get("part") else "")
                  for t in report["todo"]]
        lines += [""]
    lines += ["| Area | Status | Summary |", "|---|---|---|"]
    for r in report["results"]:
        lines.append(f"| {r['title']} | {DOT[r['status']]} {r['status']} | {r['summary'].replace('|', '/')} |")
    if report.get("compare"):
        lines += ["", f"## Changes since the last check ({report['compare_with']})", "",
                  "| Measurement | Before | Now |", "|---|---|---|"]
        lines += [f"| {c['name']} | {_fmt(c['before'])} | {_fmt(c['after'])} |" for c in report["compare"]]
    lines += ["", "## Details"]
    for r in report["results"]:
        lines += ["", f"### {r['title']}: {DOT[r['status']]} {r['status']}", "", r["summary"], ""]
        lines += [f"- **{k}**: {_fmt(v)}" for k, v in r["evidence"].items()]
    (folder / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


CSS = """
body{font-family:'Noto Sans','Noto Sans Thai',sans-serif;margin:24px auto;max-width:980px;padding:0 16px;color:#202124;background:#fff}
h1{font-size:1.5em;margin-bottom:4px} .meta{color:#5f6368;margin-top:0}
table{border-collapse:collapse;width:100%;margin:12px 0} td,th{border-bottom:1px solid #e0e0e0;padding:6px 8px;text-align:left;vertical-align:top}
.st{font-weight:600;white-space:nowrap} .badge{display:inline-block;width:12px;height:12px;border-radius:50%;margin-right:6px;vertical-align:middle}
.ev{font-family:monospace;font-size:.85em;color:#3c4043;word-break:break-word}
.overall{padding:10px 14px;border-radius:8px;color:#fff;font-weight:600;display:inline-block}
@media print{body{margin:0;max-width:none}}
"""


def _badge(status):
    return f'<span class="badge" style="background:{COLORS[status]}"></span>'


def write_html(report, folder):
    e = html.escape
    o = report["overall"]
    rows = "".join(f"<tr><td>{e(r['title'])}</td><td class=st style='color:{COLORS[r['status']]}'>{_badge(r['status'])}{e(r['status'])}</td>"
                   f"<td>{e(r['summary'])}</td></tr>" for r in report["results"])
    comp = ""
    if report.get("compare"):
        comp = (f"<h2>Changes since the last check ({e(report['compare_with'])})</h2><table><tr><th>Measurement</th><th>Before</th><th>Now</th></tr>"
                + "".join(f"<tr><td>{e(c['name'])}</td><td>{e(_fmt(c['before']))}</td><td>{e(_fmt(c['after']))}</td></tr>" for c in report["compare"])
                + "</table>")
    todo_html = ""
    if report.get("todo"):
        todo_html = ("<h2>What to do</h2><table>" + "".join(
            f"<tr><td class=st style='color:{COLORS[t['status']]}'>{_badge(t['status'])}{e(t['title'])}</td>"
            f"<td>{e(t['action'])}" + (f"<br><span class=ev>Part: {e(t['part'])}</span>" if t.get("part") else "")
            + "</td></tr>" for t in report["todo"]) + "</table>")
    details = "".join(
        f"<h3>{_badge(r['status'])}{e(r['title'])}</h3><p>{e(r['summary'])}</p><table>"
        + "".join(f"<tr><td>{e(k)}</td><td class=ev>{e(_fmt(v))}</td></tr>" for k, v in r["evidence"].items())
        + "</table>" for r in report["results"])
    doc = (f"<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
           f"<title>Chiron report: {e(machine_name(report))}</title><style>{CSS}</style></head><body>"
           f"<h1>{e(machine_name(report))}</h1><p class=meta>Chiron Stick report · {e(report['created'])} · Chiron {e(report['chiron'])}</p>"
           f"<p class=overall style='background:{COLORS[o]}'>Overall: {e(o)}</p>{todo_html}"
           f"<table><tr><th>Area</th><th>Status</th><th>Summary</th></tr>{rows}</table>{comp}<h2>Details</h2>{details}</body></html>")
    (folder / "report.html").write_text(doc, encoding="utf-8")


OWNER_CSS = """
@page{size:A4;margin:14mm}
body{font-family:'Noto Sans Thai','Noto Sans',sans-serif;margin:24px auto;max-width:860px;padding:0 16px;color:#202124;background:#fff;font-size:15px}
h1{font-size:1.45em;margin:0} .sub{color:#5f6368;margin:2px 0 14px}
.overall{border-radius:10px;padding:12px 16px;color:#fff;margin:10px 0 16px} .overall .th{font-size:1.15em;font-weight:700}
table{border-collapse:collapse;width:100%} td{border-bottom:1px solid #e0e0e0;padding:8px 6px;vertical-align:top}
.dot{width:16px;height:16px;border-radius:50%;display:inline-block;margin-top:3px}
.lab{font-weight:600;width:28%} .lab .en,.msg .en{color:#5f6368;font-weight:400;font-size:.88em;display:block;margin-top:2px}
.st{font-size:.8em;font-weight:700;white-space:nowrap}
.foot{color:#5f6368;font-size:.8em;margin-top:16px}
.parts{border:1px solid #e0e0e0;border-radius:10px;padding:10px 14px;margin-top:14px} .parts ul{margin:6px 0 0;padding-left:4px;list-style:none} .parts li{margin:3px 0}
@media print{body{margin:0;max-width:none}}
"""


def owner_lines(report):
    """(status, message key, params) for each owner-facing result, in a fixed order."""
    lines = [(r["status"], r["owner"]["key"], r["owner"]["params"]) for r in report["results"] if r.get("owner")]
    return sorted(lines, key=lambda l: OWNER_ORDER.index(l[1].split(".")[0]) if l[1].split(".")[0] in OWNER_ORDER else 99)


def write_owner_summary(report, folder):
    e = html.escape
    th, en = catalog("th"), catalog("en")
    o = report["overall"]
    parts = [t for t in report.get("todo", []) if t.get("part")]
    parts_html = ""
    if parts:
        parts_html = (f"<div class=parts><b>{e(th['ui.parts'])} · {e(en['ui.parts'])}</b><ul>"
                      + "".join(f"<li><span class=dot style='background:{COLORS[t['status']]};width:10px;height:10px'></span> "
                                f"{e(t['part'])}</li>" for t in parts) + "</ul></div>")
    rows = ""
    for status, key, params in owner_lines(report):
        area = key.split(".")[0]
        rows += (f"<tr><td style='width:22px'><span class=dot style='background:{COLORS[status]}'></span></td>"
                 f"<td class=lab>{e(th.get('label.' + area, area))}<span class=en>{e(en.get('label.' + area, area))}</span>"
                 f"<span class=st style='color:{COLORS[status]}'>{e(th.get('ui.status.' + status, ''))} · {e(en.get('ui.status.' + status, ''))}</span></td>"
                 f"<td class=msg>{e(message(th, key, params))}<span class=en>{e(message(en, key, params))}</span></td></tr>")
    doc = (f"<!doctype html><html lang=th><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
           f"<title>{e(th['ui.title'])} · {e(en['ui.title'])}</title><style>{OWNER_CSS}</style></head><body>"
           f"<h1>{e(th['ui.title'])} · {e(en['ui.title'])}</h1>"
           f"<p class=sub>{e(th['ui.machine'])} / {e(en['ui.machine'])}: <b>{e(machine_name(report))}</b> · "
           f"{e(th['ui.checked'])} / {e(en['ui.checked'])} {e(report['created'][:16].replace('T', ' '))}</p>"
           f"<div class=overall style='background:{COLORS[o]}'><div class=th>{e(th['overall.' + o])}</div>"
           f"<div>{e(en['overall.' + o])}</div></div><table>{rows}</table>{parts_html}"
           f"<p class=foot>{e(th['ui.footer'])}<br>{e(en['ui.footer'])}</p></body></html>")
    (folder / "owner-summary.html").write_text(doc, encoding="utf-8")


def write_all(report, folder):
    folder.mkdir(parents=True, exist_ok=True)
    report["overall"] = overall(report["results"])
    report["todo"] = todo(report["results"])
    write_json(report, folder)
    write_markdown(report, folder)
    write_html(report, folder)
    write_owner_summary(report, folder)
