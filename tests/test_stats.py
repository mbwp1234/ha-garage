"""stats.py tests: fill-up detection, economy, battery at rest."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
_SPEC = importlib.util.spec_from_file_location("g_stats", ROOT / "custom_components" / "garage" / "stats.py")
stats = importlib.util.module_from_spec(_SPEC)
sys.modules["g_stats"] = stats
_SPEC.loader.exec_module(stats)

TANK = 80.0


def test_slosh_is_not_a_refuel():
    s = stats.empty()
    stats.on_fuel(s, 40.0, 1000, "t1", TANK)
    assert stats.on_fuel(s, 43.5, 1001, "t2", TANK) is None
    assert s["refuels"] == [] and s["fuel_last"]["litres"] == 43.5


def test_a_fill_up_is_recorded_with_before_and_after():
    s = stats.empty()
    stats.on_fuel(s, 20.0, 1000, "t1", TANK)
    ev = stats.on_fuel(s, 78.0, 1002, "t2", TANK)
    assert ev == {"at": "t2", "odometer": 1002, "before": 20.0, "after": 78.0}


def test_economy_needs_a_quarter_tank_and_is_none_before():
    s = stats.empty()
    stats.on_fuel(s, 10.0, 1000, "t1", TANK)
    stats.on_fuel(s, 78.0, 1000, "t2", TANK)
    assert stats.economy(s, TANK, 1050, 74.0)["mpg"] is None          # 4 L used: not enough
    # 37.854 L = 10 gal used over 200 mi -> 20 mpg, from the open segment
    e = stats.economy(s, TANK, 1200, 78.0 - 37.854)
    assert e["mpg"] == 20.0 and e["segments"] == 1


def test_economy_from_closed_segments_weighted_by_miles():
    s = stats.empty()
    stats.on_fuel(s, 10.0, 0, "a", TANK)
    stats.on_fuel(s, 78.0, 0, "b", TANK)            # fill 1
    stats.on_fuel(s, 78.0 - 37.854, 200, "c", TANK)
    stats.on_fuel(s, 78.0, 200, "d", TANK)          # fill 2: 10 gal over 200 mi
    stats.on_fuel(s, 78.0 - 37.854, 500, "e", TANK)
    stats.on_fuel(s, 78.0, 500, "f", TANK)          # fill 3: 10 gal over 300 mi
    e = stats.economy(s, TANK)
    assert e["segments"] == 2 and e["mpg"] == 25.0  # 500 mi / 20 gal


def test_battery_rest_rejects_nonsense():
    s = stats.empty()
    stats.on_battery_sleep(s, 12.62, "t1")
    stats.on_battery_sleep(s, 0.0, "t2")
    stats.on_battery_sleep(s, 99.0, "t3")
    assert s["rest"] == [{"at": "t1", "v": 12.62}]


def test_range_is_none_without_economy():
    assert stats.range_miles(40.0, None) is None
    assert stats.range_miles(None, 20.0) is None
    assert stats.range_miles(37.854, 20.0) == 200
