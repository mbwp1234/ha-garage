"""Schedule + engine tests: plain pytest, no Home Assistant needed.

Run: python -m pytest tests
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
_SPEC = importlib.util.spec_from_file_location("g_schedule", ROOT / "custom_components" / "garage" / "schedule.py")
sched = importlib.util.module_from_spec(_SPEC)
sys.modules["g_schedule"] = sched
_SPEC.loader.exec_module(sched)

TACOMA = sched.load_schedule("toyota_tacoma_3g")
POSTER = json.loads((ROOT / "tests" / "fixtures" / "maintenance_map_tacoma_3g.json").read_text())
TODAY = date(2026, 6, 1)


def by_n(statuses):
    return {s.n: s for s in statuses}


# ------------------------------------------------------------ alignment with the printed map

def _expected_from_poster():
    """The poster minus its known slips."""
    out = {}
    quirks = POSTER["quirks"]
    for k, col in POSTER["columns"].items():
        q = quirks.get(k, {})
        out[int(k)] = {
            "normal": sorted(set(col["normal"]) - set(q.get("normal", []))),
            "severe": sorted(set(col["severe"]) - set(q.get("severe", []))),
        }
    return out


def test_schedule_reproduces_every_poster_column():
    generated = sched.poster_columns(TACOMA)
    expected = _expected_from_poster()
    assert sorted(generated) == sorted(expected), "poster covers 5k..300k in 5k steps"
    bad = {m: (generated[m], expected[m]) for m in expected if generated[m] != expected[m]}
    assert not bad, f"schedule disagrees with the printed map at: {bad}"


def test_poster_quirks_are_exactly_what_the_intervals_cannot_produce():
    """Every listed quirk must really be absent from the generated chart, and present on the poster.
    A quirk that the engine DOES produce would mean the list is stale."""
    generated = sched.poster_columns(TACOMA)
    for k, q in POSTER["quirks"].items():
        if k.startswith("_"):
            continue
        m = int(k)
        for kind in ("normal", "severe"):
            for n in q.get(kind, []):
                assert n in POSTER["columns"][k][kind], f"quirk {n}@{k} not on the poster"
                assert n not in generated[m][kind], f"quirk {n}@{k} is produced by the schedule"


def test_alignment_test_can_fail():
    """Guard against an assertion that never runs: break one interval and the comparison must fail."""
    broken = json.loads(json.dumps(TACOMA))
    for it in broken["items"]:
        if it["n"] == 11:
            it["first"] = 60000          # the old spreadsheet's coolant figure
    generated = sched.poster_columns(broken)
    expected = _expected_from_poster()
    assert any(generated[m] != expected[m] for m in expected)


def test_every_item_has_the_maps_reference_data():
    for it in TACOMA["items"]:
        assert it["name"] and it["short"] and it["zone"] in TACOMA["zones"], it["n"]
        assert it["kind"] in sched.RESETS
        assert isinstance(it.get("parts"), list) and isinstance(it.get("torque"), list)
    assert [it["n"] for it in TACOMA["items"]] == list(range(1, 17))


# ------------------------------------------------------------ engine

def entry(odo, d, *items, deleted=False):
    e = {"id": f"e{odo}", "date": d, "odometer": odo,
         "items": [{"n": n, "action": a} for n, a in items]}
    if deleted:
        e["deleted"] = True
    return e


def test_overdue_soon_ok_and_nolog():
    log = [
        entry(40000, "2025-06-01", (1, "changed"), (2, "rotated")),
        entry(31000, "2024-09-01", (7, "changed")),
    ]
    st = by_n(sched.compute(TACOMA, log, 45200, TODAY, profiles={"1": "severe"}))
    assert st[1].status == "over" and st[1].remaining == -200          # 40k + 5k severe
    assert st[2].status == "over"                                         # 45k
    assert st[7].status == "ok" and st[7].remaining == 15800            # 31k + 30k normal
    assert st[3].status == "nolog" and st[3].remaining is None          # first due 20k passed, never logged
    assert st[11].status == "ok" and st[11].remaining == 100000 - 45200  # coolant: not due yet is not "no record"


def test_nolog_is_never_a_number():
    st = by_n(sched.compute(TACOMA, [], 85000, TODAY))
    for n in (3, 4, 5, 13, 14, 16):
        assert st[n].status == "nolog" and st[n].remaining is None


def test_severe_profile_only_where_the_map_has_one():
    st = by_n(sched.compute(TACOMA, [], 1000, TODAY, profiles={"1": "severe", "9": "severe"}))
    assert st[1].interval == 5000 and st[1].profile == "severe"
    assert st[9].interval == 120000 and st[9].profile == "normal"         # plugs have no severe figure


def test_inspection_resets_inspect_items_but_not_change_items():
    log = [entry(50000, "2025-01-01", (14, "inspected"), (1, "inspected"))]
    st = by_n(sched.compute(TACOMA, log, 52000, TODAY))
    assert st[14].last_odometer == 50000
    assert st[1].last_odometer is None


def test_deleted_entries_do_not_count():
    log = [entry(50000, "2025-01-01", (1, "changed"), deleted=True)]
    st = by_n(sched.compute(TACOMA, log, 52000, TODAY))
    assert st[1].last_odometer is None


def test_coolant_every_50k_after_the_first():
    log = [entry(100500, "2025-01-01", (11, "changed"))]
    st = by_n(sched.compute(TACOMA, log, 120000, TODAY))
    assert st[11].due_at == 150500


def test_month_limit_makes_an_item_due_by_date():
    log = [entry(50000, "2025-06-01", (1, "changed"))]
    st = by_n(sched.compute(TACOMA, log, 51000, TODAY, profiles={"1": "severe"}, months={"1": 6}))
    assert st[1].due_date == "2025-12-01" and st[1].status == "over"


def test_pace_and_eta():
    log = [entry(10000, "2025-12-03", (1, "changed"))]         # 180 days before TODAY
    st = by_n(sched.compute(TACOMA, log, 13600, TODAY, profiles={"1": "severe"}))
    assert st[1].remaining == 1400
    assert st[1].eta == "2026-08-10"                            # 20 mi/day -> 70 days


def test_summary_counts_and_next():
    log = [entry(40000, "2025-06-01", (1, "changed"), (2, "rotated"))]
    s = sched.summary(sched.compute(TACOMA, log, 44800, TODAY, profiles={"1": "severe"}))
    assert s["over"] == 0
    assert s["next"]["n"] in (1, 2) and s["next"]["remaining"] == 200


@pytest.mark.parametrize("interval,window", [(5000, (500, 30)), (15000, (1000, 45)), (30000, (1500, 60)),
                                             (60000, (2000, 60)), (100000, (3000, 90))])
def test_soon_windows(interval, window):
    assert sched.soon_window(interval) == window


# ------------------------------------------------------------ the Kona: Hyundai's "miles or months"

KONA = sched.load_schedule("hyundai_kona_os_16t_awd")


def test_kona_schedule_is_well_formed():
    assert [it["n"] for it in KONA["items"]] == list(range(1, 13))
    for it in KONA["items"]:
        assert it["zone"] in KONA["zones"] and it["kind"] in sched.RESETS, it["n"]
        assert isinstance(it["parts"], list) and isinstance(it["torque"], list)


def test_kona_figures_match_the_2022_manual():
    k = {it["id"]: it for it in KONA["items"]}
    assert (k["oil"]["normal"], k["oil"]["severe"], k["oil"]["months"], k["oil"]["severe_months"]) == (8000, 5000, 12, 6)
    assert k["plugs"]["normal"] == 48000 and k["cabin"]["normal"] == 16000 and k["air"]["normal"] == 24000
    assert (k["coolant"]["first"], k["coolant"]["normal"], k["coolant"]["months"]) == (120000, 24000, 24)
    assert k["dct"]["kind"] == "inspect" and k["dct"]["normal"] == 40000
    assert k["tcase"]["normal"] == k["rdiff"]["normal"] == 32000


def test_schedule_months_apply_and_severe_months_follow_the_profile():
    log = [entry(40000, "2025-10-01", (1, "changed"))]
    normal = by_n(sched.compute(KONA, log, 41000, TODAY))[1]
    severe = by_n(sched.compute(KONA, log, 41000, TODAY, profiles={"1": "severe"}))[1]
    assert normal.months == 12 and normal.due_date == "2026-10-01" and normal.status == "ok"
    assert severe.months == 6 and severe.due_date == "2026-04-01" and severe.status == "over"
    # a settings override still wins
    assert by_n(sched.compute(KONA, log, 41000, TODAY, months={"1": 3}))[1].months == 3


def test_tacoma_still_has_no_month_limits():
    log = [entry(50000, "2020-01-01", (1, "changed"))]
    assert by_n(sched.compute(TACOMA, log, 50100, TODAY))[1].due_date is None


def test_kona_with_no_mileage_is_all_nolog_not_zero():
    st = sched.compute(KONA, [], None, TODAY)
    assert {s.status for s in st} == {"nolog"} and all(s.remaining is None for s in st)
