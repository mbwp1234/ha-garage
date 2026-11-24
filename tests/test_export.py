"""export.py: the service record handed to a buyer."""
from __future__ import annotations

import csv
import html
import importlib.util
import io
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parents[1] / "custom_components" / "garage"


def _load(name):
    spec = importlib.util.spec_from_file_location(f"g_{name}", ROOT / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"g_{name}"] = mod
    spec.loader.exec_module(mod)
    return mod


sched = _load("schedule")
ex = _load("export")
S = sched.load_schedule("toyota_tacoma_3g")
TODAY = date(2026, 6, 1)

LOG = [
    {"id": "a1", "date": "2024-01-10", "odometer": 40000, "items": [{"n": 1, "action": "changed"}, {"n": 2, "action": "rotated"}],
     "by": "dealer", "notes": "Dealer 40k", "cost": None, "user": "Somebody At Home", "source": "app"},
    {"id": "a2", "date": "2024-07-02", "odometer": 45100, "items": [{"n": 1, "action": "changed"}, {"n": 14, "action": "inspected", "measure": 7}],
     "by": "self", "notes": "", "cost": 61.5, "edited": True},
    {"id": "a3", "date": "2024-09-09", "odometer": None, "items": [{"n": 3, "action": "changed"}], "by": "", "notes": ""},
    {"id": "gone", "date": "2025-01-01", "odometer": 48000, "items": [{"n": 9, "action": "changed"}], "deleted": True,
     "notes": "SHOULD NOT APPEAR"},
]


def _history(page):
    return page.split("Service history</h2>")[1]


def _page(costs=False, info=None, odo=50000):
    st = sched.compute(S, [e for e in LOG if not e.get("deleted")], odo, TODAY, {"1": "severe"})
    return ex.build_html(S, LOG, st, "Tacoma", odo, TODAY, info, costs)


def test_record_leaves_out_people_ids_and_deleted_entries():
    page = _page()
    for leak in ("Somebody At Home", "SHOULD NOT APPEAR", '"a1"', ">a1<", "48,000"):
        assert leak not in page
    assert "Dealer 40k" in page


def test_missing_mileage_is_a_dash_not_zero():
    page = _history(_page())
    row = page.split("Sep 9, 2024")[1].split("</tr>")[0]
    assert "—" in row and ">0<" not in row
    rows = list(csv.reader(io.StringIO(ex.build_csv(S, LOG))))
    cabin = next(r for r in rows if r[0] == "2024-09-09")
    assert cabin[1] == ""


def test_missing_odometer_reads_as_a_dash():
    assert "<b>— mi</b>" in _page(odo=None)


def test_corrected_entry_is_marked_and_footnoted():
    page = _page()
    assert page.count("†") == 2                       # the mark on the row and the footnote
    assert "corrected after it was first recorded" in page
    rows = list(csv.reader(io.StringIO(ex.build_csv(S, LOG))))
    assert next(r for r in rows if r[0] == "2024-07-02")[-1] == "yes"


def test_no_footnote_without_a_corrected_entry():
    log = [{k: v for k, v in e.items() if k != "edited"} for e in LOG]
    st = sched.compute(S, log, 50000, TODAY)
    assert "†" not in ex.build_html(S, log, st, "Tacoma", 50000, TODAY)


def test_costs_only_when_asked_and_present():
    assert "$61.50" not in _page()
    assert "$61.50" in _page(costs=True)
    assert "Cost" not in ex.build_csv(S, LOG).splitlines()[0]
    assert "Cost" in ex.build_csv(S, LOG, costs=True).splitlines()[0]
    no_costs = [{**e, "cost": None} for e in LOG]
    st = sched.compute(S, no_costs, 50000, TODAY)
    assert ">Cost<" not in ex.build_html(S, no_costs, st, "Tacoma", 50000, TODAY, costs=True)


def test_newest_first_and_every_item_named():
    page = _history(_page())
    assert page.index("Sep 9, 2024") < page.index("Jul 2, 2024") < page.index("Jan 10, 2024")
    for it in S["items"]:
        assert html.escape(it["name"]) in _page()
    assert "Front brake pad — inspected (7)" in page


def test_vehicle_identity_from_settings():
    page = _page(info={"year": 2019, "make": "Toyota", "model": "Tacoma", "vin": "TESTVIN0000000000"})
    assert "2019 Toyota Tacoma" in page and "TESTVIN0000000000" in page
    assert "VIN" not in _page()                        # no VIN row when none is set
    assert ex.filename("2019 Toyota Tacoma", TODAY, "html") == "2019-toyota-tacoma-service-record-2026-06-01.html"


def test_oil_pace_is_a_rollup():
    page = _page()
    assert "5,100 mi" in page                          # 40,000 -> 45,100, one gap
    assert "2</b><span>oil changes" in page


def test_template_braces_are_all_escaped():
    # A stray single brace in the CSS would make str.format raise at export time.
    assert _page().startswith("<!doctype html>")


def test_store_saves_exports(tmp_path):
    store = _load("store")
    (tmp_path / "share").mkdir()
    gs = store.GarageStore(store.StoreConfig(str(tmp_path / "share"), "v", require_mount=False), {1})
    out = gs.save_export({"a.html": "<p>x</p>", "a.csv": "x\n"})
    assert (Path(out) / "a.html").read_text() == "<p>x</p>"
    import pytest
    with pytest.raises(store.GarageError):
        gs.save_export({"../evil.html": "x"})


def test_panel_opens_the_url_the_view_serves():
    js = (ROOT / "frontend" / "garage-panel.js").read_text()
    init = (ROOT / "__init__.py").read_text()
    assert "data-act=\"export\"" in js and "a === 'export'" in js and "this._export()" in js
    assert "type: 'garage/export'" in js and "'/record.html'" in js
    assert 'url = "/api/garage/{entry_id}/record.{ext}"' in init
    assert "register_view(GarageRecordView())" in init
    assert "register_command(hass, ws_export)" in init
