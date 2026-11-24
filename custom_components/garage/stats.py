"""Fuel economy, fill-ups and the battery at rest, learned from the vehicle's own sensors.

Plain Python, no Home Assistant imports. The state is a small dict the integration keeps
in `stats.json` beside the log:

    fuel_last   the last real tank reading {litres, odometer, at}; survives the dongle sleeping
    refuels     detected fill-ups {at, odometer, before, after}
    rest        battery voltage at rest {at, v}: the last reading before the dongle slept

Nothing here is ever a zero standing in for a missing reading: a value that cannot be
known yet is None, and the caller draws it as missing.
"""
from __future__ import annotations

from typing import Any

L_PER_GAL = 3.785411784
MAX_REFUELS = 60
MAX_REST = 120


def empty() -> dict[str, Any]:
    return {"version": 1, "fuel_last": None, "refuels": [], "rest": []}


def refuel_threshold(tank_l: float | None) -> float:
    """A rise this big between two readings is a fill-up, not fuel sloshing in the tank."""
    return max(8.0, 0.10 * tank_l) if tank_l else 8.0


def on_fuel(state: dict[str, Any], litres: float, odometer: float | None, at: str,
            tank_l: float | None) -> dict[str, Any] | None:
    """Feed one real tank reading. Returns the refuel event if this reading is one."""
    if litres is None or litres < 0:
        return None
    last = state.get("fuel_last")
    event = None
    if last is not None and litres - float(last["litres"]) >= refuel_threshold(tank_l):
        event = {"at": at, "odometer": odometer, "before": round(float(last["litres"]), 1), "after": round(litres, 1)}
        state.setdefault("refuels", []).append(event)
        state["refuels"] = state["refuels"][-MAX_REFUELS:]
    state["fuel_last"] = {"litres": round(litres, 1), "odometer": odometer, "at": at}
    return event


def on_battery_sleep(state: dict[str, Any], volts: float, at: str) -> None:
    """The dongle's last voltage before it slept — a few minutes after shutdown, so every
    sample is taken the same way and they are comparable."""
    if volts is None or not 9.0 <= volts <= 16.0:
        return
    state.setdefault("rest", []).append({"at": at, "v": round(volts, 2)})
    state["rest"] = state["rest"][-MAX_REST:]


def economy(state: dict[str, Any], tank_l: float | None, odometer: float | None = None,
            litres_now: float | None = None, last_n: int = 3) -> dict[str, Any]:
    """Miles per gallon from tank-to-tank segments that used at least a quarter tank.

    A segment runs from one fill-up (its level AFTER) to the next (its level BEFORE). The
    open segment since the last fill-up counts too once a quarter tank is gone. The newest
    `last_n` segments are averaged weighted by miles. None until a segment qualifies.
    """
    refs = [r for r in state.get("refuels", []) if r.get("odometer") is not None]
    floor_l = 0.25 * tank_l if tank_l else 15.0
    segs: list[tuple[float, float]] = []
    for a, b in zip(refs, refs[1:]):
        used = float(a["after"]) - float(b["before"])
        miles = float(b["odometer"]) - float(a["odometer"])
        if used >= floor_l and miles > 0:
            segs.append((miles, used))
    if refs and odometer is not None and litres_now is not None:
        a = refs[-1]
        used = float(a["after"]) - float(litres_now)
        miles = float(odometer) - float(a["odometer"])
        if used >= floor_l and miles > 0:
            segs.append((miles, used))
    segs = segs[-last_n:]
    if not segs:
        return {"mpg": None, "segments": 0}
    miles = sum(m for m, _ in segs)
    gal = sum(u for _, u in segs) / L_PER_GAL
    return {"mpg": round(miles / gal, 1) if gal > 0 else None, "segments": len(segs)}


def range_miles(litres: float | None, mpg: float | None) -> float | None:
    if litres is None or mpg is None:
        return None
    return round(litres / L_PER_GAL * mpg)
