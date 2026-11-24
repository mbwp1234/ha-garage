"""The service record: what you hand a buyer when the vehicle is sold.

Plain Python, no Home Assistant imports. Builds a self-contained, printable HTML page
(print it, or save it as a PDF from the print dialog) and a CSV of the same history.

What goes in: the vehicle, the odometer at export, where every scheduled item stands, and
every logged service, newest first. What stays out: who in the house logged an entry, entry
ids, and deleted entries. Costs only when asked for (and only when any were ever recorded).

Rules carried from the rest of the app:
  - a missing mileage is "—", never 0
  - an entry corrected after it was first logged is marked, with a footnote saying so
"""
from __future__ import annotations

import csv
import html
import io
from datetime import date
from typing import Any

VERB = {"changed": "Replaced", "inspected": "Inspected", "rotated": "Rotated", "greased": "Greased"}
BY = {"self": "Owner", "dealer": "Dealer", "shop": "Shop", "": ""}
STATUS = {"ok": "Up to date", "soon": "Due soon", "over": "Overdue", "nolog": "No record"}


def _fmt(n: float | int | None) -> str:
    return "—" if n is None else f"{int(round(n)):,}"


def _date(d: str | None) -> str:
    if not d:
        return "—"
    try:
        x = date.fromisoformat(d)
    except ValueError:
        return d
    return f"{x:%b} {x.day}, {x.year}"


def _month(d: str) -> str:
    try:
        return f"{date.fromisoformat(d):%b %Y}"
    except ValueError:
        return d


def _e(s: Any) -> str:
    return html.escape("" if s is None else str(s))


def vehicle_title(name: str, info: dict[str, Any] | None) -> str:
    info = info or {}
    parts = [str(info[k]) for k in ("year", "make", "model", "trim") if info.get(k)]
    return " ".join(parts) or name


def _work(entry: dict[str, Any], by_n: dict[int, dict[str, Any]]) -> list[str]:
    out = []
    for it in entry.get("items", []):
        sc = by_n.get(int(it.get("n", -1)))
        name = sc["name"] if sc else f"Item {it.get('n')}"
        verb = VERB.get(it.get("action") or "", "")
        # An inspection that ended in a replacement is said plainly; a rotation is "Tire rotation, rotated".
        if sc and sc["kind"] in ("rotate", "grease"):
            line = name
        elif sc and sc["kind"] == "inspect":
            line = f"{name.removesuffix(' check')} — {verb.lower() or 'inspected'}"
        else:
            line = f"{name} — {verb.lower() or 'replaced'}"
        if it.get("measure") not in (None, ""):
            line += f" ({it['measure']})"
        out.append(line)
    return out


def _sorted(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    live = [e for e in entries if not e.get("deleted")]
    return sorted(live, key=lambda e: (e.get("date") or "", e.get("odometer") if e.get("odometer") is not None else -1),
                  reverse=True)


def _oil_pace(entries: list[dict[str, Any]], oil_n: int | None) -> tuple[int, int | None]:
    """(how many oil changes, average miles between them). None when fewer than two have a mileage."""
    if oil_n is None:
        return 0, None
    odos = sorted(e["odometer"] for e in entries if e.get("odometer") is not None and not e.get("deleted")
                  and any(int(i.get("n", -1)) == oil_n and i.get("action") == "changed" for i in e.get("items", [])))
    count = sum(1 for e in entries if not e.get("deleted")
                and any(int(i.get("n", -1)) == oil_n and i.get("action") == "changed" for i in e.get("items", [])))
    if len(odos) < 2:
        return count, None
    return count, int(round((odos[-1] - odos[0]) / (len(odos) - 1)))


def has_costs(entries: list[dict[str, Any]]) -> bool:
    return any(e.get("cost") is not None for e in entries if not e.get("deleted"))


def build_csv(schedule: dict[str, Any], entries: list[dict[str, Any]], costs: bool = False) -> str:
    by_n = {int(it["n"]): it for it in schedule["items"]}
    costs = costs and has_costs(entries)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Date", "Odometer (mi)", "Work performed", "Performed by", "Notes"] + (["Cost"] if costs else []) + ["Corrected"])
    for e in _sorted(entries):
        row = [e.get("date") or "", "" if e.get("odometer") is None else int(e["odometer"]),
               "; ".join(_work(e, by_n)), BY.get(e.get("by") or "", ""), e.get("notes") or ""]
        if costs:
            row.append("" if e.get("cost") is None else f"{e['cost']:.2f}")
        row.append("yes" if e.get("edited") else "")
        w.writerow(row)
    return buf.getvalue()


def build_html(schedule: dict[str, Any], entries: list[dict[str, Any]], statuses: list[Any],
               name: str, odometer: float | None, today: date,
               info: dict[str, Any] | None = None, costs: bool = False) -> str:
    """`statuses` are schedule.ItemStatus (or their as_dict()); `info` is settings['vehicle']."""
    info = info or {}
    by_n = {int(it["n"]): it for it in schedule["items"]}
    rows = _sorted(entries)
    costs = costs and has_costs(entries)
    title = vehicle_title(name, info)
    sts = [s if isinstance(s, dict) else s.as_dict() for s in statuses]

    dated = [e["date"] for e in rows if e.get("date")]
    span = f"{_month(min(dated))} – {_month(max(dated))}" if dated else "—"
    oil = next((it["n"] for it in schedule["items"] if it["id"] == "oil"), None)
    oil_count, oil_every = _oil_pace(rows, oil)

    ident = []
    if info.get("vin"):
        ident.append(f"<div><span>VIN</span><b class=mono>{_e(info['vin'])}</b></div>")
    ident.append(f"<div><span>Odometer</span><b>{_fmt(odometer)} mi</b></div>")
    ident.append(f"<div><span>Record date</span><b>{_e(_date(today.isoformat()))}</b></div>")

    facts = [f"<div><b>{len(rows)}</b><span>services logged</span></div>",
             f"<div><b>{_e(span)}</b><span>first – latest</span></div>"]
    if oil_count:
        facts.append(f"<div><b>{oil_count}</b><span>oil changes</span></div>")
    if oil_every:
        facts.append(f"<div><b>{_fmt(oil_every)} mi</b><span>average between oil changes</span></div>")

    stat_rows = []
    for s in sorted(sts, key=lambda s: s["n"]):
        sc = by_n.get(int(s["n"]), {})
        every = f"{_fmt(s['interval'])} mi"
        if s.get("profile") == "severe":
            every += " <i>severe-service</i>"
        if sc.get("first") and not s.get("last_date"):
            every = f"first at {_fmt(sc['first'])}, then {every}"
        if s.get("last_date") or s.get("last_odometer") is not None:
            last = f"{_e(_date(s.get('last_date')))}<small>{_fmt(s.get('last_odometer'))} mi</small>"
        else:
            last = "<span class=dim>No record</span>"
        st = s["status"]
        if st == "ok" and not s.get("last_date"):
            label = "Not yet due"
        else:
            label = STATUS.get(st, st)
        due = "—" if s.get("due_at") is None or st == "nolog" else f"{_fmt(s['due_at'])} mi"
        stat_rows.append(f"<tr><td>{_e(sc.get('name', s.get('name')))}</td><td>{every}</td><td>{last}</td>"
                         f"<td class=num>{due}</td><td><span class='st {st}'>{_e(label)}</span></td></tr>")

    any_edit = False
    log_rows = []
    for e in rows:
        mark = ""
        if e.get("edited"):
            any_edit = True
            mark = "<sup title='Corrected after it was first recorded'>†</sup>"
        work = "".join(f"<li>{_e(w)}</li>" for w in _work(e, by_n))
        note = f"<div class=note>{_e(e['notes'])}</div>" if e.get("notes") else ""
        cost = ""
        if costs:
            c = e.get("cost")
            cost = "<td class=num>" + ("—" if c is None else f"${c:,.2f}") + "</td>"
        log_rows.append(f"<tr><td class=when>{_e(_date(e.get('date')))}{mark}</td><td class=num>{_fmt(e.get('odometer'))}</td>"
                        f"<td><ul>{work}</ul>{note}</td><td>{_e(BY.get(e.get('by') or '', ''))}</td>{cost}</tr>")
    if not log_rows:
        log_rows.append(f"<tr><td colspan={5 if costs else 4} class=dim>Nothing has been logged.</td></tr>")

    foot = [f"Maintenance schedule: {_e(schedule.get('title', ''))}."]
    if any_edit:
        foot.append("† Entry corrected after it was first recorded.")
    foot.append(f"Prepared {_e(_date(today.isoformat()))} from the owner’s maintenance log.")

    return TEMPLATE.format(
        title=_e(title), ident="".join(ident), facts="".join(facts),
        status="".join(stat_rows), log="".join(log_rows),
        cost_head="<th class=num>Cost</th>" if costs else "",
        foot="".join(f"<p>{f}</p>" for f in foot),
    )


def filename(name: str, today: date, ext: str) -> str:
    slug = "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-") or "vehicle"
    while "--" in slug:
        slug = slug.replace("--", "-")
    return f"{slug}-service-record-{today.isoformat()}.{ext}"


TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · Service record</title>
<style>
:root{{--ink:#1c2430;--dim:#5d6876;--rule:#d9dee5;--soft:#f3f5f8;--ok:#2f7d4f;--soon:#9a6a00;--over:#b3261e;--none:#5d6876}}
*{{box-sizing:border-box}}
html{{background:#e9edf2}}
body{{margin:0 auto;max-width:820px;background:#fff;color:var(--ink);font:13px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;padding:40px 44px 32px}}
header{{display:flex;justify-content:space-between;align-items:flex-end;gap:24px;border-bottom:2px solid var(--ink);padding-bottom:14px}}
.eyebrow{{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--dim);font-weight:600}}
h1{{font-size:26px;line-height:1.15;margin:4px 0 0;font-weight:700}}
.ident{{display:flex;gap:22px;text-align:right}}
.ident div{{display:flex;flex-direction:column}}
.ident span,.facts span{{font-size:11px;color:var(--dim)}}
.ident b{{font-size:14px}}
.mono{{font-family:ui-monospace,Menlo,Consolas,monospace;letter-spacing:.04em}}
.facts{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:1px;background:var(--rule);border:1px solid var(--rule);border-radius:8px;overflow:hidden;margin:18px 0 8px}}
.facts div{{background:var(--soft);padding:10px 14px;display:flex;flex-direction:column}}
.facts b{{font-size:16px}}
h2{{font-size:12px;letter-spacing:.1em;text-transform:uppercase;margin:26px 0 8px;color:var(--dim)}}
table{{width:100%;border-collapse:collapse}}
th{{text-align:left;font-size:11px;font-weight:600;color:var(--dim);border-bottom:1px solid var(--ink);padding:6px 8px}}
td{{padding:7px 8px;border-bottom:1px solid var(--rule);vertical-align:top}}
tr{{break-inside:avoid}}
td small{{display:block;color:var(--dim)}}
td i{{font-style:normal;color:var(--dim);font-size:11px}}
.num{{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}}
.when{{white-space:nowrap}}
.dim{{color:var(--dim)}}
ul{{margin:0;padding:0;list-style:none}}
li+li{{margin-top:1px}}
.note{{color:var(--dim);font-style:italic;margin-top:3px}}
sup{{color:var(--dim);margin-left:2px}}
.st{{display:inline-block;font-size:11px;font-weight:600;padding:1px 8px;border-radius:999px;border:1px solid currentColor;white-space:nowrap}}
.st.ok{{color:var(--ok)}}.st.soon{{color:var(--soon)}}.st.over{{color:var(--over)}}.st.nolog{{color:var(--none);border-style:dashed}}
footer{{margin-top:24px;padding-top:10px;border-top:1px solid var(--rule);color:var(--dim);font-size:11px}}
footer p{{margin:2px 0}}
.bar{{position:sticky;top:0;display:flex;justify-content:flex-end;margin:-28px -32px 12px}}
.bar button{{font:600 13px/1 inherit;font-family:inherit;background:var(--ink);color:#fff;border:0;border-radius:999px;padding:10px 16px;cursor:pointer}}
@media (max-width:640px){{body{{padding:24px 16px}}header{{flex-direction:column;align-items:flex-start}}.ident{{text-align:left;flex-wrap:wrap}}.bar{{margin:-12px 0 8px}}
  .status td:nth-child(2),.status th:nth-child(2){{display:none}}}}
@media print{{html{{background:#fff}}body{{padding:0;max-width:none;font-size:11.5px}}.bar{{display:none}}@page{{margin:14mm 14mm 16mm}}h2{{break-after:avoid}}}}
</style></head>
<body>
<div class="bar"><button onclick="window.print()">Print or save as PDF</button></div>
<header><div><div class="eyebrow">Service record</div><h1>{title}</h1></div><div class="ident">{ident}</div></header>
<div class="facts">{facts}</div>
<h2>Where everything stands</h2>
<table class="status"><thead><tr><th>Item</th><th>Interval</th><th>Last done</th><th class=num>Next due</th><th>Status</th></tr></thead><tbody>{status}</tbody></table>
<h2>Service history</h2>
<table><thead><tr><th>Date</th><th class=num>Miles</th><th>Work performed</th><th>By</th>{cost_head}</tr></thead><tbody>{log}</tbody></table>
<footer>{foot}</footer>
</body></html>
"""
