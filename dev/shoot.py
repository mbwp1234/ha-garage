"""Render the panel in headless Chromium against a vehicle folder and take screenshots.

    python dev/shoot.py <vehicle-folder> <odometer> [--tiles states.json]

The folder holds log.json / settings.json / truck.png exactly as on the share. Nothing is
written back. Shots land in dev/out/ (git-ignored: they show real data).
Needs playwright (pip install playwright; playwright install chromium).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parents[1]
COMP = ROOT / "custom_components" / "garage"
OUT = ROOT / "dev" / "out"


def _load(name):
    spec = importlib.util.spec_from_file_location(f"g_{name}", COMP / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"g_{name}"] = mod
    spec.loader.exec_module(mod)
    return mod


def fixture(folder: Path, odometer: float | None, schedule_id: str, states: dict, battery: str | None = None,
            name: str | None = None, typed: bool = False, others: list | None = None) -> dict:
    sched = _load("schedule")
    s = sched.load_schedule(schedule_id)
    log = json.loads((folder / "log.json").read_text())["entries"] if (folder / "log.json").exists() else []
    log = [e for e in log if not e.get("deleted")]
    settings = json.loads((folder / "settings.json").read_text()) if (folder / "settings.json").exists() else {}
    today = date.today()
    st = sched.compute(s, log, odometer, today, settings.get("profile", {}), settings.get("months", {}))
    pace = sched.pace_per_day(log, odometer, today)
    gst = _load("stats")
    st_file = folder / "stats.json"
    stats = json.loads(st_file.read_text()) if st_file.exists() else gst.empty()
    last = stats.get("fuel_last") or {}
    eco = gst.economy(stats, 79.9, odometer, last.get("litres"))
    mpg = eco["mpg"] or settings.get("mpg")
    vehicle = {
        "entry_id": "dev", "name": name or ("Tacoma" if "taco" in folder.name.lower() else "Example"), "error": None,
        "storage": {"mounted": True, "exists": True, "has_log": True}, "odometer": odometer,
        "odometer_as_of": "2026-01-01T00:00:00+00:00", "odometer_entity": None if typed else "sensor.dev_odometer",
        "fuel_entity": None if typed else "sensor.dev_fuel", "tank_l": 79.9,
        "fuel": None, "schedule": s, "summary": sched.summary(st, len(log)), "pace": None if pace is None else round(pace, 1),
        "points": sorted([e["date"], e["odometer"]] for e in log if e.get("odometer") is not None),
        "items": [x.as_dict() for x in st],
        "economy": {"mpg": eco["mpg"], "segments": eco["segments"], "range": gst.range_miles(last.get("litres"), mpg),
                    "range_basis": ("learned" if eco["mpg"] else "assumed") if mpg else None, "litres": last.get("litres"),
                    "as_of": last.get("at"), "percent": None},
        "refuels": stats.get("refuels", [])[-12:], "rest": stats.get("rest", [])[-40:], "battery_entity": battery,
    }
    me = {"entry_id": "dev", "name": vehicle["name"], "summary": vehicle["summary"]}
    vs = [me] + [{"entry_id": f"other{i}", "name": o[0], "summary": {"over": o[1], "soon": o[2], "nolog": o[3]}}
                 for i, o in enumerate(others or [])]
    return {"vehicles": vs, "vehicle": vehicle, "log": log,
            "settings": settings, "states": states}


HARNESS = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>html,body{margin:0;height:100%}</style></head><body>
<script src="/panel.js"></script>
<script>
var FIX = __FIX__;
function st(v, unit, age){ var t = new Date(Date.now() - (age || 0) * 1000).toISOString(); return {state: v == null ? 'unavailable' : String(v), attributes: {unit_of_measurement: unit}, last_updated: t, last_reported: t}; }
var states = {}; Object.keys(FIX.states).forEach(function(k){ var x = FIX.states[k]; states[k] = st(x[0], x[1], x[2]); });
var hass = { states: states, themes: {darkMode: __DARK__},
  callWS: async function(m){ if (m.type === 'garage/get') return FIX; return {result: {id: 'x'}, vehicle: FIX.vehicle}; },
  callApi: async function(){ return []; },
  fetchWithAuth: function(u){ return fetch('/truck.png'); } };
var tag = [...document.querySelectorAll('script')].length && Object.keys(window).length;
customElements.whenDefined('__TAG__').then(function(){
  var el = document.createElement('__TAG__'); el.hass = hass; el.narrow = __NARROW__; document.body.appendChild(el); window.el = el; });
</script></body></html>"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("odometer", help="miles, or 'none' for no reading")
    ap.add_argument("--name")
    ap.add_argument("--typed", action="store_true", help="no odometer sensor: mileage is typed in")
    ap.add_argument("--other", action="append", default=[], help="another vehicle for the tabs: Name:over:soon:nolog")
    ap.add_argument("--schedule", default="toyota_tacoma_3g")
    ap.add_argument("--tiles", help="JSON {entity_id: [value, unit, age_seconds?]} for the stat tiles")
    ap.add_argument("--item", type=int, default=1, help="which item's sheet to shoot")
    ap.add_argument("--battery", help="the dongle supply-voltage entity (battery_entity option)")
    a = ap.parse_args()
    from playwright.sync_api import sync_playwright

    folder = Path(a.folder)
    states = json.loads(Path(a.tiles).read_text()) if a.tiles else {}
    odo = None if a.odometer.lower() == "none" else float(a.odometer)
    others = [[o.split(":")[0]] + [int(x) for x in o.split(":")[1:4]] for o in a.other]
    fix = fixture(folder, odo, a.schedule, states, a.battery, a.name, a.typed, others)
    panel = (COMP / "frontend" / "garage-panel.js").read_text()
    ver = panel.split("var VERSION = '")[1].split("'")[0]
    tag = "garage-panel-" + ver.replace(".", "-")
    img = next((folder / n for n in ("truck.png", "truck.jpg", "vehicle.png", "vehicle.jpg") if (folder / n).exists()), None)
    OUT.mkdir(parents=True, exist_ok=True)

    def page_for(pw_page, dark, narrow):
        html = (HARNESS.replace("__FIX__", json.dumps(fix)).replace("__DARK__", "true" if dark else "false")
                .replace("__NARROW__", "true" if narrow else "false").replace("__TAG__", tag))

        def route(r):
            u = r.request.url
            if u.endswith("/panel.js"):
                r.fulfill(body=panel, content_type="application/javascript")
            elif u.endswith("/truck.png") and img:
                r.fulfill(body=img.read_bytes(), content_type="image/png")
            elif u.startswith("http://garage.test/"):
                r.fulfill(body=html, content_type="text/html")
            else:
                r.continue_()
        pw_page.route("**/*", route)
        errors = []
        pw_page.on("pageerror", lambda e: errors.append(str(e)))
        pw_page.on("console", lambda m: m.type == "error" and errors.append(m.text))
        pw_page.goto("http://garage.test/index.html")
        pw_page.wait_for_timeout(900)
        return errors

    with sync_playwright() as p:
        b = p.chromium.launch()
        shots = []
        for name, w, h, dark, narrow in [("phone-light", 390, 2700, False, True), ("phone-dark", 390, 2700, True, True),
                                         ("desktop", 1400, 1500, False, False)]:
            pg = b.new_page(viewport={"width": w, "height": h}, device_scale_factor=2 if w < 500 else 1)
            errs = page_for(pg, dark, narrow)
            sw = pg.evaluate("() => { const r = el.shadowRoot.querySelector('.scroll'); return [r.scrollWidth, r.clientWidth]; }")
            pg.screenshot(path=str(OUT / f"{name}.png"))
            shots.append((name, errs, sw))
            pg.close()
        pg = b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
        errs = page_for(pg, False, True)
        for nm, sel in [("sheet-item", f"[data-act=item][data-n='{a.item}']"), ("sheet-log", "[data-act=log]"),
                        ("sheet-map", "[data-act=poster]"), ("sheet-catchup", "[data-act=catchup]"),
                        ("sheet-edit", "[data-act=edit]"), ("sheet-odo", "[data-act=odo]")]:
            if nm == "sheet-item":  # any item, even one the list has folded away
                pg.evaluate("n => el._open({ kind: 'item', n: n })", a.item)
            else:
                if not pg.evaluate("s => !!el.shadowRoot.querySelector(s)", sel):
                    continue
                pg.evaluate("s => el.shadowRoot.querySelector(s).click()", sel)
            pg.wait_for_timeout(500)
            pg.screenshot(path=str(OUT / f"{nm}.png"))
            pg.evaluate("() => el.shadowRoot.querySelector('[data-act=close].x').click()")
            pg.wait_for_timeout(400)
        shots.append(("sheets", errs, None))
        b.close()
    for name, errs, sw in shots:
        print(name, "errors:", errs or "none", "scroll(w,client):", sw)


if __name__ == "__main__":
    main()
